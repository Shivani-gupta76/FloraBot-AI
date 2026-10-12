from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.security import create_access_token, decode_subject, hash_password, verify_password
from app.db.database import get_db
from app.db.models import Alert, AlertType, ConfidenceStatus as ModelConfidence, DiseaseDetection, Plant, RobotTelemetry, SensorReading, User, UserRole, WateringEvent
from app import schemas as s
from app.services.inference import InvalidImage, MAX_IMAGE_BYTES, ModelUnavailable, classify_image, inference_status

api = APIRouter(prefix="/api")
oauth = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def current_user(token: str | None = Depends(oauth), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = int(decode_subject(token))
    except (JWTError, ValueError):
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "Invalid user")
    return user

def admin_user(user: User = Depends(current_user)):
    if user.role != UserRole.admin:
        raise HTTPException(403, "Administrator access required")
    return user

def exists_plant(db: Session, plant_id: int | None):
    if plant_id is not None and not db.get(Plant, plant_id):
        raise HTTPException(404, "Plant not found")

@api.post("/auth/register", response_model=s.TokenOut, status_code=201)
def register(data: s.RegisterIn, db: Session = Depends(get_db)):
    # Admin accounts are provisioned out of band with app.bootstrap_admin.
    user = User(email=data.email.lower(), full_name=data.full_name, password_hash=hash_password(data.password), role=UserRole.operator)
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "Email is already registered")
    db.refresh(user)
    return {"access_token": create_access_token(str(user.id))}

@api.post("/auth/login", response_model=s.TokenOut)
def login(data: s.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": create_access_token(str(user.id))}

@api.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role.value}

@api.get("/plants", response_model=list[s.PlantOut])
def list_plants(db: Session = Depends(get_db), _=Depends(current_user)):
    return db.scalars(select(Plant).order_by(Plant.id)).all()

@api.post("/plants", response_model=s.PlantOut, status_code=201)
def create_plant(data: s.PlantIn, db: Session = Depends(get_db), _=Depends(current_user)):
    row = Plant(**data.model_dump()); db.add(row); db.commit(); db.refresh(row); return row

@api.get("/plants/{plant_id}", response_model=s.PlantOut)
def get_plant(plant_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    row = db.get(Plant, plant_id)
    if not row: raise HTTPException(404, "Plant not found")
    return row

@api.put("/plants/{plant_id}", response_model=s.PlantOut)
def update_plant(plant_id: int, data: s.PlantIn, db: Session = Depends(get_db), _=Depends(current_user)):
    row = db.get(Plant, plant_id)
    if not row: raise HTTPException(404, "Plant not found")
    for key, value in data.model_dump().items(): setattr(row, key, value)
    db.commit(); db.refresh(row); return row

@api.delete("/plants/{plant_id}", status_code=204)
def delete_plant(plant_id: int, db: Session = Depends(get_db), _=Depends(admin_user)):
    row = db.get(Plant, plant_id)
    if not row: raise HTTPException(404, "Plant not found")
    db.delete(row); db.commit()

@api.post("/detections", response_model=s.DetectionOut, status_code=201)
def create_detection(data: s.DetectionIn, db: Session = Depends(get_db), _=Depends(current_user)):
    exists_plant(db, data.plant_id)
    row = DiseaseDetection(**data.model_dump()); db.add(row)
    if data.plant_id:
        plant = db.get(Plant, data.plant_id); plant.last_scanned_at = data.detected_at
    db.commit(); db.refresh(row)
    if data.confidence_status == s.ConfidenceStatus.UNCERTAIN or data.confidence_status == s.ConfidenceStatus.REVIEW_RECOMMENDED:
        db.add(Alert(alert_type=AlertType.low_confidence, message="Detection requires review", plant_id=data.plant_id, details={"detection_id": row.id, "class_name": data.class_name, "confidence_status": data.confidence_status.value})); db.commit()
    elif not data.class_name.endswith("_Healthy"):
        db.add(Alert(alert_type=AlertType.disease_detected, message="Disease class reported by inference service", plant_id=data.plant_id, details={"detection_id": row.id, "class_name": data.class_name})); db.commit()
    return row

@api.get("/inference/status")
def get_inference_status(_=Depends(current_user)):
    return inference_status()

@api.post("/detections/infer", response_model=s.DetectionOut, status_code=201)
async def infer_detection(request: Request, plant_id: int | None = None, db: Session = Depends(get_db), _=Depends(current_user)):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(415, "Upload a leaf image using an image content type.")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Choose an image smaller than 10 MB.")
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Choose an image smaller than 10 MB.")
    image_bytes = bytes(chunks)
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(413 if len(image_bytes) > MAX_IMAGE_BYTES else 422, "Choose a readable image smaller than 10 MB.")
    exists_plant(db, plant_id)
    try:
        prediction = classify_image(image_bytes)
    except InvalidImage as error:
        raise HTTPException(422, str(error)) from error
    except ModelUnavailable as error:
        raise HTTPException(503, str(error)) from error
    data = s.DetectionIn(
        plant_id=plant_id,
        class_name=str(prediction["class_name"]),
        confidence=float(prediction["confidence"]),
        confidence_status=s.ConfidenceStatus(str(prediction["confidence_status"])),
        detected_at=datetime.now(timezone.utc),
        model_version=str(prediction["model_version"]),
    )
    # Uploaded images are processed in memory and are not persisted by this endpoint.
    return create_detection(data, db, None)

@api.get("/detections", response_model=list[s.DetectionOut])
def list_detections(plant_id: int | None = None, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(DiseaseDetection).order_by(DiseaseDetection.detected_at.desc()).limit(limit)
    if plant_id is not None: stmt = stmt.where(DiseaseDetection.plant_id == plant_id)
    return db.scalars(stmt).all()

@api.get("/detections/{detection_id}", response_model=s.DetectionOut)
def get_detection(detection_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    row = db.get(DiseaseDetection, detection_id)
    if not row: raise HTTPException(404, "Detection not found")
    return row

@api.post("/sensors/readings", response_model=s.SensorOut, status_code=201)
def create_reading(data: s.SensorIn, db: Session = Depends(get_db), _=Depends(current_user)):
    row = SensorReading(**data.model_dump()); db.add(row); db.commit(); db.refresh(row); return row

@api.get("/sensors/latest")
def latest_readings(robot_id: str | None = None, db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(SensorReading).order_by(SensorReading.recorded_at.desc())
    if robot_id: stmt = stmt.where(SensorReading.robot_id == robot_id)
    rows = db.scalars(stmt).all()
    latest = {}
    for row in rows: latest.setdefault((row.robot_id, row.sensor_type), row)
    return list(latest.values())

@api.get("/sensors/history", response_model=list[s.SensorOut])
def sensor_history(robot_id: str | None = None, sensor_type: str | None = None, since: datetime | None = None, limit: int = Query(default=500, ge=1, le=5000), db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(SensorReading).order_by(SensorReading.recorded_at.desc()).limit(limit)
    if robot_id: stmt = stmt.where(SensorReading.robot_id == robot_id)
    if sensor_type: stmt = stmt.where(SensorReading.sensor_type == sensor_type)
    if since: stmt = stmt.where(SensorReading.recorded_at >= since)
    return db.scalars(stmt).all()

@api.post("/watering", response_model=s.WateringOut, status_code=201)
def create_watering(data: s.WateringIn, db: Session = Depends(get_db), _=Depends(current_user)):
    exists_plant(db, data.plant_id)
    row = WateringEvent(**data.model_dump()); db.add(row)
    if data.plant_id:
        plant = db.get(Plant, data.plant_id); plant.last_watered_at = data.ended_at or data.started_at
    db.commit(); db.refresh(row); return row

@api.get("/watering/history", response_model=list[s.WateringOut])
def watering_history(robot_id: str | None = None, plant_id: int | None = None, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(WateringEvent).order_by(WateringEvent.started_at.desc()).limit(limit)
    if robot_id: stmt = stmt.where(WateringEvent.robot_id == robot_id)
    if plant_id is not None: stmt = stmt.where(WateringEvent.plant_id == plant_id)
    return db.scalars(stmt).all()

@api.post("/robot/telemetry", response_model=s.TelemetryOut, status_code=201)
def create_telemetry(data: s.TelemetryIn, db: Session = Depends(get_db), _=Depends(current_user)):
    row = RobotTelemetry(**data.model_dump()); db.add(row); db.commit(); db.refresh(row)
    alert_types = {"LOW_BATTERY": AlertType.low_battery, "LOW_WATER": AlertType.low_water, "ERROR": AlertType.system_error, "OFFLINE": AlertType.robot_offline}
    if data.robot_state and data.robot_state.value in alert_types:
        db.add(Alert(alert_type=alert_types[data.robot_state.value], message=f"Robot reported state {data.robot_state.value}", robot_id=data.robot_id, details={"telemetry_id": row.id, "robot_state": data.robot_state.value}))
        db.commit()
    return row

@api.get("/robot/status")
def robot_status(robot_id: str | None = None, db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(RobotTelemetry).order_by(RobotTelemetry.recorded_at.desc())
    if robot_id: stmt = stmt.where(RobotTelemetry.robot_id == robot_id)
    rows = db.scalars(stmt).all(); latest = {}
    for row in rows: latest.setdefault(row.robot_id, row)
    return list(latest.values())

@api.get("/alerts", response_model=list[s.AlertOut])
def list_alerts(unread_only: bool = False, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), _=Depends(current_user)):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if unread_only: stmt = stmt.where(Alert.is_read.is_(False))
    return db.scalars(stmt).all()

@api.put("/alerts/{alert_id}/read", response_model=s.AlertOut)
def mark_alert_read(alert_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    row = db.get(Alert, alert_id)
    if not row: raise HTTPException(404, "Alert not found")
    row.is_read = True; db.commit(); db.refresh(row); return row

@api.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), _=Depends(current_user)):
    return {
      "plant_count": db.scalar(select(func.count(Plant.id))) or 0,
      "detection_count": db.scalar(select(func.count(DiseaseDetection.id))) or 0,
      "watering_event_count": db.scalar(select(func.count(WateringEvent.id))) or 0,
      "unread_alert_count": db.scalar(select(func.count(Alert.id)).where(Alert.is_read.is_(False))) or 0,
      "latest_sensor_readings": db.scalars(select(SensorReading).order_by(SensorReading.recorded_at.desc()).limit(20)).all(),
      "latest_robot_telemetry": db.scalars(select(RobotTelemetry).order_by(RobotTelemetry.recorded_at.desc()).limit(20)).all(),
      "latest_detection_at": db.scalar(select(func.max(DiseaseDetection.detected_at))),
    }
