from io import BytesIO
from pathlib import Path

from PIL import Image

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 50_000_000
MIN_SIDE = 200

_FORMATS = {
    "JPEG": ("image/jpeg", {".jpg", ".jpeg"}),
    # Pillow reports JPEGs with extra embedded images (common from phones and cameras) as MPO.
    "MPO": ("image/jpeg", {".jpg", ".jpeg"}),
    "PNG": ("image/png", {".png"}),
}
_EXTENSIONS = {ext for _, exts in _FORMATS.values() for ext in exts}
_MIME_TYPES = {mime for mime, _ in _FORMATS.values()}


class InvalidImage(ValueError):
    pass


def validate_image(filename: str, content_type: str, data: bytes) -> str:
    """Check an upload is a real, decodable JPEG or PNG and return its MIME type."""
    extension = Path(filename).suffix.lower()
    if extension not in _EXTENSIONS or content_type not in _MIME_TYPES:
        raise InvalidImage("Please upload a JPG, JPEG or PNG image.")
    if not data:
        raise InvalidImage("The uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise InvalidImage("The image is larger than 10 MB.")

    try:
        with Image.open(BytesIO(data)) as image:
            detected_format = image.format
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise InvalidImage("The image has too many pixels.")
            image.load()
    except InvalidImage:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        raise InvalidImage("The file could not be read as an image.") from error

    if detected_format not in _FORMATS:
        raise InvalidImage("Please upload a JPG, JPEG or PNG image.")
    mime_type, extensions = _FORMATS[detected_format]
    if mime_type != content_type or extension not in extensions:
        raise InvalidImage("This file doesn't look like a real JPG or PNG image.")
    if min(width, height) < MIN_SIDE:
        raise InvalidImage(f"The image is too small. Use at least {MIN_SIDE}×{MIN_SIDE} pixels.")
    return mime_type
