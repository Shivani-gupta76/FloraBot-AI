from __future__ import annotations

from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
import re
from threading import Lock

from app.core.config import settings
from app.schemas import CLASSES

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "flora_bot_best.pt"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
_model_lock = Lock()
_loaded_model = None
_loaded_path: Path | None = None


class ModelUnavailable(RuntimeError):
    pass


class InvalidImage(ValueError):
    pass


def model_path() -> Path:
    configured_path = settings.inference_model_path
    return Path(configured_path).expanduser() if configured_path else DEFAULT_MODEL_PATH


def inference_status() -> dict[str, str | bool | None]:
    path = model_path()
    if not path.is_file():
        return {"available": False, "reason": "Model file not found. Configure FLORABOT_MODEL_PATH or place flora_bot_best.pt in backend/models/.", "model_version": None}
    try:
        runtime_available = find_spec("ultralytics") is not None and find_spec("PIL") is not None
    except (ImportError, ValueError):
        runtime_available = False
    if not runtime_available:
        return {"available": False, "reason": "The optional Ultralytics and Pillow inference runtimes are not installed.", "model_version": None}
    return {"available": True, "reason": None, "model_version": path.stem}


def _get_model():
    global _loaded_model, _loaded_path
    path = model_path()
    if not path.is_file():
        raise ModelUnavailable("The classifier model is not configured on this backend.")
    try:
        from ultralytics import YOLO
    except (ImportError, ModuleNotFoundError) as error:
        raise ModelUnavailable("The optional Ultralytics inference runtime is not installed.") from error
    with _model_lock:
        if _loaded_model is None or _loaded_path != path:
            try:
                _loaded_model = YOLO(str(path))
            except Exception as error:
                _loaded_model = None
                _loaded_path = None
                raise ModelUnavailable("The configured classifier could not be loaded.") from error
            _loaded_path = path
        return _loaded_model


def _normalize_class(name: str) -> str | None:
    normalize = lambda value: re.sub(r"_+", "_", value.replace(" ", "_").replace(".", "_")).strip("_").casefold()
    known = {normalize(class_name): class_name for class_name in CLASSES}
    return known.get(normalize(name))


def classify_image(image_bytes: bytes) -> dict[str, str | float]:
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise InvalidImage("Choose an image smaller than 10 MB.")
    try:
        from PIL import Image, UnidentifiedImageError
    except (ImportError, ModuleNotFoundError) as error:
        raise ModelUnavailable("The optional Pillow image runtime is not installed.") from error
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise InvalidImage("The uploaded file is not a readable image.") from error

    model = _get_model()
    try:
        with _model_lock:
            prediction = model.predict(source=image, verbose=False)[0]
        probabilities = prediction.probs
        if probabilities is None:
            raise ModelUnavailable("The configured model is not a classification model.")
        class_names = prediction.names
        raw_name = class_names[int(probabilities.top1)]
        class_name = _normalize_class(str(raw_name))
        if not class_name:
            raise ModelUnavailable("The model output does not match the supported Flora-Bot classes.")
        confidence = float(probabilities.top1conf)
        confidence_status = "HIGH_CONFIDENCE" if confidence >= 0.8 else "REVIEW_RECOMMENDED" if confidence >= 0.5 else "UNCERTAIN"
        return {"class_name": class_name, "confidence": confidence, "confidence_status": confidence_status, "model_version": model_path().stem}
    except ModelUnavailable:
        raise
    except Exception as error:
        raise ModelUnavailable("The classifier could not complete inference for this image.") from error
