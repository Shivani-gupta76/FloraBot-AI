import os
import tempfile
from io import BytesIO
from pathlib import Path

os.environ["FLORABOT_DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'test.db'}"
os.environ["FLORABOT_DEVICE_MODE"] = "real"
os.environ["FLORABOT_DEVICE_TOKEN"] = "test-device-token-0123456789"
os.environ["FLORABOT_DEVICE_ID"] = "esp32-test"
os.environ["FLORABOT_VISION_PROVIDER"] = "mock"
os.environ["FLORABOT_MOCK_DELAY_SECONDS"] = "0"
os.environ["FLORABOT_DISEASE_CLASSIFIER"] = "mock"

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings

# Keep a developer's backend/.env out of the tests; must run before anything reads the settings.
Settings.model_config["env_file"] = None

from app.db import Base, engine
from app.main import app

DEVICE_HEADERS = {"Authorization": "Bearer test-device-token-0123456789"}


def image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (400, 300)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (40, 140, 60)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def client(fresh_db):
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
