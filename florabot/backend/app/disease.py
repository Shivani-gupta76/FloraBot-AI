from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Protocol

from PIL import Image, ImageOps

from app.config import Settings
from app.decision import Confidence


@dataclass(frozen=True)
class DiseasePrediction:
    label: str
    confidence: float
    alternatives: list[str]
    scores: tuple[tuple[str, float], ...] = ()


class DiseaseClassifier(Protocol):
    """Adapter for a leaf-disease model. It is separate from watering and never drives an LED."""

    name: str
    labels: list[str]

    def classify(self, image: bytes) -> DiseasePrediction: ...


class YoloClassifier:
    """The trained YOLO11n classifier for 15 tomato, potato and pepper leaf conditions."""

    def __init__(self, model_path: Path):
        # Ultralytics pulls in PyTorch, which takes seconds to import, so only load it when this model is used.
        from ultralytics import YOLO

        self.name = model_path.stem
        self._model = YOLO(str(model_path))
        self.labels = list(self._model.names.values())
        self._lock = Lock()

    def classify(self, image: bytes) -> DiseasePrediction:
        with Image.open(BytesIO(image)) as picture:
            rgb = ImageOps.exif_transpose(picture).convert("RGB")
        with self._lock:
            result = self._model.predict(source=rgb, verbose=False)[0]
        ranked = [(result.names[index], float(result.probs.data[index])) for index in result.probs.top5]
        return DiseasePrediction(
            label=ranked[0][0],
            confidence=ranked[0][1],
            alternatives=[label for label, _ in ranked[1:3]],
            scores=tuple(ranked),
        )


LEAF_MODEL_LABELS = [
    "Pepper_Bacterial_Spot", "Pepper_Healthy", "Potato_Early_Blight", "Potato_Healthy", "Potato_Late_Blight",
    "Tomato_Bacterial_Spot", "Tomato_Early_Blight", "Tomato_Healthy", "Tomato_Late_Blight", "Tomato_Leaf_Mold",
    "Tomato_Mosaic_Virus", "Tomato_Septoria", "Tomato_Spider_Mites", "Tomato_Target_Spot", "Tomato_Yellow_Leaf_Curl_Virus",
]


class MockClassifier:
    name = "mock"
    labels = LEAF_MODEL_LABELS

    def classify(self, image: bytes) -> DiseasePrediction:
        return DiseasePrediction(
            "Tomato_Healthy",
            0.93,
            ["Tomato_Leaf_Mold", "Tomato_Early_Blight"],
            (("Tomato_Healthy", 0.93), ("Tomato_Leaf_Mold", 0.04), ("Tomato_Early_Blight", 0.02)),
        )


def build_classifier(settings: Settings) -> DiseaseClassifier:
    match settings.disease_classifier:
        case "yolo":
            return YoloClassifier(settings.disease_model_path)
        case "mock":
            return MockClassifier()
    raise ValueError(f"Unknown disease classifier: {settings.disease_classifier!r}")


def readable(label: str) -> tuple[str, str]:
    """'Tomato_Late_Blight' -> ('Tomato', 'Late blight')."""
    crop, _, condition = label.partition("_")
    return crop, condition.replace("_", " ").capitalize()


def confidence_level(confidence: float) -> Confidence:
    if confidence >= 0.8:
        return Confidence.HIGH
    if confidence >= 0.5:
        return Confidence.MEDIUM
    return Confidence.LOW


def describe(prediction: DiseasePrediction) -> str:
    crop, condition = readable(prediction.label)
    level = confidence_level(prediction.confidence)
    healthy = condition == "Healthy"
    if level is Confidence.LOW:
        return "I couldn't recognize this leaf."
    if level is Confidence.HIGH:
        return f"This looks like a healthy {crop.lower()} leaf." if healthy else f"This looks most like {condition.lower()} on a {crop.lower()} leaf."
    if healthy:
        return f"This might be a healthy {crop.lower()} leaf, but I'm not certain."
    return f"This might be {condition.lower()} on a {crop.lower()} leaf, but I'm not certain."
