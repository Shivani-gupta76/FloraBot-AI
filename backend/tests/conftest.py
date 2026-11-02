import os
os.environ.setdefault("SECRET_KEY", "test-signing-secret-that-is-only-for-tests")
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.database import get_db
from app.main import app

@pytest.fixture()
def isolated_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    yield testing_session
    engine.dispose()

@pytest.fixture()
def client(isolated_session_factory):
    def override_db():
        db = isolated_session_factory()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture()
def db_session(isolated_session_factory):
    session = isolated_session_factory()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture()
def admin_auth(isolated_session_factory):
    from app.core.security import create_access_token
    from app.db.models import User, UserRole

    db = isolated_session_factory()
    user = User(email="admin-test@example.com", full_name="Test Admin", password_hash="test-only-hash", role=UserRole.admin)
    db.add(user)
    db.commit()
    token = create_access_token(str(user.id))
    db.close()
    return {"Authorization": "Bearer " + token}

@pytest.fixture()
def auth(client):
    response = client.post("/api/auth/register", json={"email":"operator@example.com", "full_name":"Field Operator", "password":"strong-test-password"})
    assert response.status_code == 201
    return {"Authorization": "Bearer " + response.json()["access_token"]}
