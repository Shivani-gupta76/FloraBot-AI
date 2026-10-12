def test_auth_registration_and_login(client):
    origin = "http://localhost:5173"
    preflight = client.options("/api/auth/register", headers={"Origin":origin, "Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"authorization,content-type"})
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "POST" in preflight.headers["access-control-allow-methods"]
    assert "authorization" in preflight.headers["access-control-allow-headers"].lower()
    assert "content-type" in preflight.headers["access-control-allow-headers"].lower()
    created = client.post("/api/auth/register", headers={"Origin":origin}, json={"email":"a@example.com", "full_name":"A User", "password":"strong-password-123"})
    assert created.status_code == 201
    assert created.headers["access-control-allow-origin"] == origin
    login = client.post("/api/auth/login", headers={"Origin":origin}, json={"email":"a@example.com", "password":"strong-password-123"})
    assert login.status_code == 200
    assert login.headers["access-control-allow-origin"] == origin
    assert client.post("/api/auth/login", json={"email":"a@example.com", "password":"wrong-password"}).status_code == 401

def test_plant_create_and_update(client, auth):
    response = client.post("/api/plants", headers=auth, json={"crop_type":"Tomato", "latitude":18.5, "longitude":73.8})
    assert response.status_code == 201
    plant_id = response.json()["id"]
    assert client.get(f"/api/plants/{plant_id}", headers=auth).json()["crop_type"] == "Tomato"
    assert client.put(f"/api/plants/{plant_id}", headers=auth, json={"crop_type":"Tomato", "health_status":"observed"}).status_code == 200

def test_detection_validates_supported_class_and_saves(client, auth):
    plant = client.post("/api/plants", headers=auth, json={"crop_type":"Tomato"}).json()
    payload = {"plant_id":plant["id"], "class_name":"Tomato_Early_Blight", "confidence":0.82, "confidence_status":"HIGH_CONFIDENCE", "detected_at":"2026-01-02T03:04:05Z", "model_version":"flora-yolo11n-v1"}
    assert client.post("/api/detections", headers=auth, json=payload).status_code == 201
    payload["class_name"] = "Made_Up_Disease"
    assert client.post("/api/detections", headers=auth, json=payload).status_code == 422

def test_sensor_submission_and_validation(client, auth):
    payload = {"robot_id":"robot-A", "sensor_type":"soil_moisture", "value":41, "unit":"percent", "recorded_at":"2026-01-02T03:04:05Z"}
    assert client.post("/api/sensors/readings", headers=auth, json=payload).status_code == 201
    payload["value"] = 140
    assert client.post("/api/sensors/readings", headers=auth, json=payload).status_code == 422

def test_telemetry_watering_alerts_and_summary(client, auth):
    plant = client.post("/api/plants", headers=auth, json={"crop_type":"Pepper"}).json()
    at = "2026-01-02T03:04:05Z"
    telemetry = {"robot_id":"robot-A", "battery_level":None, "robot_state":"LOW_BATTERY", "recorded_at":at}
    assert client.post("/api/robot/telemetry", headers=auth, json=telemetry).status_code == 201
    alerts = client.get("/api/alerts", headers=auth).json()
    assert len(alerts) == 1 and alerts[0]["alert_type"] == "LOW_BATTERY"
    assert client.put(f"/api/alerts/{alerts[0]['id']}/read", headers=auth).json()["is_read"] is True
    watering = {"robot_id":"robot-A", "plant_id":plant["id"], "started_at":at, "duration_seconds":15.5, "trigger_source":"moisture_controller"}
    assert client.post("/api/watering", headers=auth, json=watering).status_code == 201
    assert client.get("/api/alerts?unread_only=true", headers=auth).json() == []
    summary = client.get("/api/dashboard/summary", headers=auth).json()
    assert summary["plant_count"] == 1 and summary["watering_event_count"] == 1
    assert summary["latest_robot_telemetry"][0]["battery_level"] is None

def test_auth_and_missing_records(client):
    assert client.get("/api/plants").status_code == 401
    account = client.post("/api/auth/register", json={"email":"b@example.com", "full_name":"B User", "password":"strong-password-123"}).json()
    headers = {"Authorization":"Bearer " + account["access_token"]}
    assert client.get("/api/plants/123", headers=headers).status_code == 404
    invalid = client.post("/api/robot/telemetry", headers=headers, json={"robot_id":"r", "latitude":100, "recorded_at":"2026-01-02T03:04:05Z"})
    assert invalid.status_code == 422

def test_inference_status_and_unavailable_model_does_not_create_records(client, auth, monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes, "inference_status", lambda: {"available": False, "reason": "No configured model.", "model_version": None})
    status = client.get("/api/inference/status", headers=auth)
    assert status.status_code == 200 and status.json()["available"] is False
    monkeypatch.setattr(routes, "classify_image", lambda _image: (_ for _ in ()).throw(routes.ModelUnavailable("No configured model.")))
    response = client.post("/api/detections/infer", headers={**auth, "Content-Type": "image/png"}, content=b"sample-image")
    assert response.status_code == 503
    assert client.get("/api/detections", headers=auth).json() == []
