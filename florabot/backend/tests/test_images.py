from io import BytesIO

import pytest
from PIL import Image

from app.images import MAX_BYTES, InvalidImage, validate_image
from tests.conftest import image_bytes


def test_accepts_jpeg_and_png():
    assert validate_image("leaf.jpg", "image/jpeg", image_bytes("JPEG")) == "image/jpeg"
    assert validate_image("leaf.JPEG", "image/jpeg", image_bytes("JPEG")) == "image/jpeg"
    assert validate_image("leaf.png", "image/png", image_bytes("PNG")) == "image/png"


@pytest.mark.parametrize(
    ("filename", "content_type", "data", "reason"),
    [
        ("leaf.gif", "image/gif", image_bytes("GIF"), "JPG, JPEG or PNG"),
        ("leaf.jpg", "image/jpeg", b"", "empty"),
        ("leaf.jpg", "image/jpeg", b"not an image at all", "could not be read"),
        ("leaf.jpg", "image/jpeg", image_bytes("JPEG")[:400], "could not be read"),
        ("leaf.jpg", "image/jpeg", image_bytes("PNG"), "doesn't look like a real JPG or PNG"),
        ("leaf.png", "image/jpeg", image_bytes("JPEG"), "doesn't look like a real JPG or PNG"),
        ("leaf.jpg", "image/jpeg", image_bytes("JPEG", (120, 120)), "too small"),
        ("leaf.jpg", "image/jpeg", b"\xff" * (MAX_BYTES + 1), "larger than 10 MB"),
    ],
)
def test_rejects_invalid_files(filename, content_type, data, reason):
    with pytest.raises(InvalidImage, match=reason):
        validate_image(filename, content_type, data)


def test_accepts_phone_style_jpeg_with_embedded_preview():
    buffer = BytesIO()
    main, preview = Image.new("RGB", (400, 300), (40, 140, 60)), Image.new("RGB", (160, 120))
    main.save(buffer, format="MPO", save_all=True, append_images=[preview])
    assert Image.open(BytesIO(buffer.getvalue())).format == "MPO"
    assert validate_image("phone.jpg", "image/jpeg", buffer.getvalue()) == "image/jpeg"
