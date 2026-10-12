import os
os.environ.setdefault("SECRET_KEY", "test-signing-secret-that-is-only-for-tests")
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.database import get_db
from app.main import app

@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    def override_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture()
def auth(client):
    response = client.post("/api/auth/register", json={"email":"operator@example.com", "full_name":"Field Operator", "password":"strong-test-password"})
    assert response.status_code == 201
    return {"Authorization": "Bearer " + response.json()["access_token"]}
