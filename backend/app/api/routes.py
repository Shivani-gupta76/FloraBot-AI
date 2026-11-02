from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import create_access_token, decode_subject, hash_password, verify_password
from app.db.database import get_db
from app.db.models import Alert, AlertType, CameraUploadRequest, ConfidenceStatus as ModelConfidence, Device, DeviceCommand, DeviceCommandStatus, DiseaseDetection, Plant, RobotTelemetry, SensorReading, User, UserRole, WateringEvent
from app import schemas as s
from app.services.device_auth import generate_device_token, hash_device_token, verify_device_token
from app.services.inference import InvalidImage, MAX_IMAGE_BYTES, ModelUnavailable, classify_image, inference_status, validate_image_bytes
from app.services.device_commands import DeviceNotCommandable, IdempotencyConflict, acknowledge_device_command, create_device_command, poll_device_command
from app.services.disease_commands import disease_led2_action, enqueue_disease_led2_command
from uuid import UUID

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

def require_camera_device(token: str | None = Header(default=None, alias="X-Device-Token")):
    configured_token = settings.camera_device_token
    if configured_token is None or not configured_token.get_secret_value():
        raise HTTPException(503, "Camera device authentication is not configured")
    if not token or not hmac.compare_digest(token.encode("utf-8"), configured_token.get_secret_value().encode("utf-8")):
        raise HTTPException(401, "Invalid device credentials")

def current_device(token: str | None = Header(default=None, alias="X-Device-Token"), db: Session = Depends(get_db)) -> Device:
    if not token:
        raise HTTPException(401, "Invalid device credentials", headers={"WWW-Authenticate": "Device"})
    candidate_hash = hash_device_token(token)
    device = db.scalar(select(Device).where(Device.credential_hash == candidate_hash))
    if not verify_device_token(token, device.credential_hash if device else None):
        raise HTTPException(401, "Invalid device credentials", headers={"WWW-Authenticate": "Device"})
    if not device.enabled or device.credential_revoked_at is not None:
        raise HTTPException(401, "Invalid device credentials", headers={"WWW-Authenticate": "Device"})
    return device

def device_is_online(device: Device, now: datetime | None = None) -> bool:
    last_seen_at = device.last_seen_at
    if not device.enabled or device.credential_revoked_at is not None or last_seen_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    return now - timedelta(seconds=settings.device_heartbeat_timeout_seconds) <= last_seen_at <= now

def device_response(device: Device, now: datetime | None = None) -> dict:
    return {
        "id": device.id,
        "device_identifier": device.device_identifier,
        "device_name": device.device_name,
        "plant_id": device.plant_id,
        "enabled": device.enabled,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
        "last_seen_at": device.last_seen_at,
        "online": device_is_online(device, now),
    }

@api.post("/devices", response_model=s.DeviceRegisteredOut, status_code=201)
def register_device(data: s.DeviceCreateIn, db: Session = Depends(get_db), _=Depends(admin_user)):
    if db.get(Plant, data.plant_id) is None:
        raise HTTPException(404, "Plant not found")
    if db.scalar(select(Device.id).where(Device.device_identifier == data.device_identifier)) is not None:
        raise HTTPException(409, "Device identifier is already registered")

    raw_token = generate_device_token()
    now = datetime.now(timezone.utc)
    device = Device(
        device_identifier=data.device_identifier,
        device_name=data.device_name,
        plant_id=data.plant_id,
        credential_hash=hash_device_token(raw_token),
        enabled=True,
    )
    db.add(device)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Device registration conflicts with existing data") from error
    db.refresh(device)
    return {**device_response(device, now), "device_token": raw_token}

@api.get("/devices", response_model=list[s.DeviceOut])
def list_devices(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(current_user),
):
    now = datetime.now(timezone.utc)
    devices = db.scalars(select(Device).order_by(Device.id).offset(offset).limit(limit)).all()
    return [device_response(device, now) for device in devices]

@api.get("/devices/{device_id}", response_model=s.DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db), _=Depends(current_user)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    return device_response(device)

@api.patch("/devices/{device_id}", response_model=s.DeviceOut)
def update_device(device_id: int, data: s.DeviceUpdateIn, db: Session = Depends(get_db), _=Depends(admin_user)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    device.enabled = data.enabled
    device.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(device)
    return device_response(device)

@api.post("/devices/{device_id}/credentials/rotate", response_model=s.DeviceCredentialRotatedOut)
def rotate_device_credential(device_id: int, db: Session = Depends(get_db), _=Depends(admin_user)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    raw_token = generate_device_token()
    now = datetime.now(timezone.utc)
    device.credential_hash = hash_device_token(raw_token)
    device.credential_version += 1
    device.credential_rotated_at = now
    device.credential_revoked_at = None
    device.updated_at = now
    db.commit()
    return {
        "device_id": device.id,
        "credential_version": device.credential_version,
        "rotated_at": now,
        "device_token": raw_token,
    }

@api.post("/devices/{device_id}/credentials/revoke", response_model=s.DeviceCredentialRevokedOut)
def revoke_device_credential(device_id: int, db: Session = Depends(get_db), _=Depends(admin_user)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    now = datetime.now(timezone.utc)
    device.credential_revoked_at = now
    device.updated_at = now
    db.commit()
    return {"device_id": device.id, "credential_revoked_at": now}

@api.post("/device/heartbeat", response_model=s.DeviceHeartbeatOut)
def device_heartbeat(device: Device = Depends(current_device), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    device.last_seen_at = now
    device.updated_at = now
    db.commit()
    return {"device_id": device.id, "last_seen_at": now, "online": True}


@api.post("/devices/{device_id}/commands", response_model=s.DeviceCommandOut)
def create_device_command_route(
    device_id: int,
    data: s.DeviceCommandCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    _=Depends(admin_user),
):
    # Plant ownership is not modeled for user accounts, so command issuance is Admin-only.
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    try:
        command, created = create_device_command(db, device, data)
    except DeviceNotCommandable:
        raise HTTPException(409, "Device is disabled or its credential is revoked")
    except IdempotencyConflict:
        raise HTTPException(409, "Idempotency key was already used for a different command")
    except ValueError as error:
        raise HTTPException(422, str(error))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return command


@api.post("/device/commands/poll", response_model=s.DeviceCommandPollOut)
def poll_device_commands(device: Device = Depends(current_device), db: Session = Depends(get_db)):
    command = poll_device_command(db, device)
    if command is None:
        return {"command": None}
    lease_expiry = min(
        command.delivered_at + timedelta(seconds=settings.device_command_lease_seconds),
        command.expires_at,
    )
    if lease_expiry.tzinfo is None:
        lease_expiry = lease_expiry.replace(tzinfo=timezone.utc)
    return {
        "command": {
            "command_id": command.command_id,
            "led_channel": command.led_channel.value,
            "desired_state": command.desired_state.value,
            "source": command.command_source,
            "reason": command.reason,
            "attempt_count": command.attempt_count,
            "lease_expires_at": lease_expiry,
            "expires_at": command.expires_at,
        }
    }


@api.post("/device/commands/{command_id}/ack", response_model=s.DeviceCommandOut)
def acknowledge_device_command_route(
    command_id: UUID,
    data: s.DeviceCommandAckIn,
    device: Device = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        command, _changed = acknowledge_device_command(
            db, device, command_id, data.success, data.failure_code
        )
    except LookupError:
        raise HTTPException(404, "Command not found")
    except TimeoutError:
        raise HTTPException(409, "Command has expired")
    except ValueError as error:
        raise HTTPException(409, str(error))
    return command


@api.get("/devices/{device_id}/commands", response_model=list[s.DeviceCommandOut])
def list_device_commands(
    device_id: int,
    led_channel: str | None = Query(default=None, pattern="^(LED1|LED2)$"),
    command_status: str | None = Query(default=None, alias="status", pattern="^(PENDING|DELIVERED|ACKNOWLEDGED|FAILED|EXPIRED)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(admin_user),
):
    if db.get(Device, device_id) is None:
        raise HTTPException(404, "Device not found")
    query = select(DeviceCommand).where(DeviceCommand.device_id == device_id)
    if led_channel is not None:
        query = query.where(DeviceCommand.led_channel == led_channel)
    if command_status is not None:
        query = query.where(DeviceCommand.status == command_status)
    return db.scalars(
        query.order_by(DeviceCommand.created_at.desc(), DeviceCommand.command_id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

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
    row, _alert, _created = persist_detection(data, db)
    return row

class CameraUploadConflict(Exception):
    pass


def _camera_upload_result(db: Session, upload: CameraUploadRequest) -> tuple[DiseaseDetection, Alert | None]:
    detection = db.get(DiseaseDetection, upload.detection_id)
    if detection is None:
        raise HTTPException(409, "The prior upload result is unavailable")
    alerts = db.scalars(
        select(Alert).where(
            Alert.plant_id == detection.plant_id,
            Alert.alert_type.in_([AlertType.disease_detected, AlertType.low_confidence]),
        )
    ).all()
    alert = next(
        (
            candidate
            for candidate in alerts
            if isinstance(candidate.details, dict)
            and str(candidate.details.get("detection_id")) == str(detection.id)
        ),
        None,
    )
    return detection, alert


def persist_detection(
    data: s.DetectionIn,
    db: Session,
    camera_idempotency: tuple[str, str] | None = None,
) -> tuple[DiseaseDetection, Alert | None, bool]:
    exists_plant(db, data.plant_id)
    if camera_idempotency is not None:
        key, image_digest = camera_idempotency
        existing = db.scalar(
            select(CameraUploadRequest).where(
                CameraUploadRequest.plant_id == data.plant_id,
                CameraUploadRequest.idempotency_key == key,
            )
        )
        if existing is not None:
            if existing.image_sha256 != image_digest:
                raise CameraUploadConflict
            detection, alert = _camera_upload_result(db, existing)
            return detection, alert, False

    led2_action = disease_led2_action(db, data.plant_id, data.class_name, data.confidence_status)
    row = DiseaseDetection(**data.model_dump()); db.add(row)
    if data.plant_id:
        plant = db.get(Plant, data.plant_id); plant.last_scanned_at = data.detected_at
    db.flush()
    alert = None
    if data.confidence_status == s.ConfidenceStatus.UNCERTAIN or data.confidence_status == s.ConfidenceStatus.REVIEW_RECOMMENDED:
        alert = Alert(alert_type=AlertType.low_confidence, message="Detection requires review", plant_id=data.plant_id, details={"detection_id": row.id, "class_name": data.class_name, "confidence_status": data.confidence_status.value}); db.add(alert)
    elif not data.class_name.endswith("_Healthy"):
        alert = Alert(alert_type=AlertType.disease_detected, message="Disease class reported by inference service", plant_id=data.plant_id, details={"detection_id": row.id, "class_name": data.class_name}); db.add(alert)
    if camera_idempotency is not None:
        key, image_digest = camera_idempotency
        db.add(CameraUploadRequest(
            plant_id=data.plant_id,
            idempotency_key=key,
            image_sha256=image_digest,
            detection_id=row.id,
        ))
    # The detection and its alert are committed together. Queueing is a separate
    # best-effort side effect so a command failure cannot erase the inference result.
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if camera_idempotency is not None:
            key, image_digest = camera_idempotency
            existing = db.scalar(
                select(CameraUploadRequest).where(
                    CameraUploadRequest.plant_id == data.plant_id,
                    CameraUploadRequest.idempotency_key == key,
                )
            )
            if existing is not None:
                if existing.image_sha256 != image_digest:
                    raise CameraUploadConflict from error
                detection, alert = _camera_upload_result(db, existing)
                return detection, alert, False
        raise
    db.refresh(row)
    if alert is not None:
        db.refresh(alert)
    if led2_action is not None:
        enqueue_disease_led2_command(db, row, led2_action)
    return row, alert, True

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

@api.post(
    "/device/camera/upload",
    response_model=s.DeviceDetectionOut,
    status_code=201,
    responses={
        200: {"model": s.DeviceDetectionOut, "description": "Idempotent retry returned the prior result."},
        409: {"description": "Idempotency key reused with different image bytes."},
    },
)
async def upload_camera_image(
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Optional stable capture identifier reused only for retries of the same JPEG.",
        max_length=128,
    ),
    db: Session = Depends(get_db),
    _device=Depends(require_camera_device),
):
    plant_id = settings.camera_plant_id
    if plant_id is None or plant_id < 1:
        raise HTTPException(503, "Camera plant is not configured")

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "image/jpeg":
        raise HTTPException(415, "Upload a JPEG image using image/jpeg content type.")

    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise HTTPException(422, "Idempotency-Key must contain 1 to 128 characters.")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Choose an image smaller than 10 MB.")

    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Choose an image smaller than 10 MB.")
    image_bytes = bytes(chunks)
    if not image_bytes:
        raise HTTPException(422, "Upload a non-empty JPEG image.")

    try:
        image_digest = hashlib.sha256(image_bytes).hexdigest()
        camera_idempotency = (idempotency_key, image_digest) if idempotency_key is not None else None
        if camera_idempotency is not None:
            existing = db.scalar(
                select(CameraUploadRequest).where(
                    CameraUploadRequest.plant_id == plant_id,
                    CameraUploadRequest.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.image_sha256 != image_digest:
                    raise CameraUploadConflict
                detection, alert = _camera_upload_result(db, existing)
                response.status_code = 200
                return _camera_detection_response(detection, alert, plant_id)

        validate_image_bytes(image_bytes, expected_format="JPEG")
        exists_plant(db, plant_id)
        prediction = classify_image(image_bytes)
    except InvalidImage as error:
        raise HTTPException(422, str(error)) from error
    except ModelUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except CameraUploadConflict:
        raise HTTPException(409, "Idempotency-Key was already used for a different image.")

    data = s.DetectionIn(
        plant_id=plant_id,
        class_name=str(prediction["class_name"]),
        confidence=float(prediction["confidence"]),
        confidence_status=s.ConfidenceStatus(str(prediction["confidence_status"])),
        detected_at=datetime.now(timezone.utc),
        model_version=str(prediction["model_version"]),
    )
    try:
        detection, alert, created = persist_detection(data, db, camera_idempotency)
    except CameraUploadConflict:
        raise HTTPException(409, "Idempotency-Key was already used for a different image.")
    if not created:
        response.status_code = 200
    return _camera_detection_response(detection, alert, plant_id)


def _camera_detection_response(detection: DiseaseDetection, alert: Alert | None, plant_id: int) -> dict:
    alert_summary = None if alert is None else {
        "id": alert.id,
        "alert_type": alert.alert_type.value,
        "message": alert.message,
        "created_at": alert.created_at,
    }
    return {
        "detection_id": detection.id,
        "plant_id": plant_id,
        "predicted_class": detection.class_name,
        "confidence": detection.confidence,
        "confidence_status": detection.confidence_status.value,
        "model_version": detection.model_version,
        "detected_at": detection.detected_at,
        "alert": alert_summary,
    }

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
