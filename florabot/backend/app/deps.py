from fastapi import Request

from app.devices import DummyDevice, RealDevice
from app.disease import DiseaseClassifier
from app.vision.base import VisionProvider


def get_provider(request: Request) -> VisionProvider:
    return request.app.state.vision


def get_device(request: Request) -> RealDevice | DummyDevice:
    return request.app.state.device


def get_classifier(request: Request) -> DiseaseClassifier:
    return request.app.state.disease
