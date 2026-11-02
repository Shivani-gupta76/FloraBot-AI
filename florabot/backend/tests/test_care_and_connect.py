import time

import pytest

from app.config import Settings
from app.deps import get_provider
from app.main import app
from app.ratelimit import RateLimiter
from app.routes import connect
from app.vision.mock import MOCK_CARE_ANSWER
from tests.conftest import image_bytes


class CareProvider:
    name = "fake"

    def __init__(self, answer: str = "", error: Exception | None = None):
        self.answer, self.error, self.questions = answer, error, []

    def analyze(self, image: bytes, mime_type: str, model=None) -> str:
        raise NotImplementedError

    def answer_question(self, question: str, model=None) -> str:
        self.questions.append(question)
        if self.error:
            raise self.error
        return self.answer


def test_mock_provider_answers_care_questions(client):
    response = client.post("/api/care/answers", json={"question": "  How often should I water a fern?  "})
    assert response.status_code == 200
    assert response.json() == {"answer": MOCK_CARE_ANSWER, "provider": "mock"}


def test_care_question_is_trimmed_and_passed_to_the_provider(client):
    provider = CareProvider(answer="  Water when the top 2 cm are dry.\n")
    app.dependency_overrides[get_provider] = lambda: provider
    response = client.post("/api/care/answers", json={"question": "  When to water?  "})
    assert response.json() == {"answer": "Water when the top 2 cm are dry.", "provider": "fake"}
    assert provider.questions == ["When to water?"]


@pytest.mark.parametrize("provider", [CareProvider(error=TimeoutError("slow")), CareProvider(answer="   ")], ids=["error", "empty"])
def test_care_answers_fail_politely(client, provider):
    app.dependency_overrides[get_provider] = lambda: provider
    response = client.post("/api/care/answers", json={"question": "Why are leaves yellow?"})
    assert response.status_code == 503
    assert response.json()["detail"] == "The plant-care assistant is unavailable right now. Please try again in a moment."


@pytest.mark.parametrize("question", ["", " a ", "x" * 501])
def test_care_question_length_is_checked(client, question):
    assert client.post("/api/care/answers", json={"question": question}).status_code == 422


def test_rate_limits_protect_the_ai(client):
    app.state.rate_limiters["care"] = RateLimiter(2)
    app.state.rate_limiters["analyses"] = RateLimiter(1)
    for _ in range(2):
        assert client.post("/api/care/answers", json={"question": "Light needs?"}).status_code == 200
    limited = client.post("/api/care/answers", json={"question": "Light needs?"})
    assert limited.status_code == 429
    assert limited.json()["detail"] == "You're sending requests too quickly. Please wait a minute and try again."

    upload = {"image": ("leaf.jpg", image_bytes(), "image/jpeg")}
    assert client.post("/api/analyses", files=upload).status_code == 202
    assert client.post("/api/analyses", files=upload).status_code == 429


def test_rate_limiter_window_slides():
    limiter = RateLimiter(1, window_seconds=0.05)
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    time.sleep(0.06)
    assert limiter.allow("a")


@pytest.mark.parametrize("listening", [True, False])
def test_connect_gives_a_phone_url_and_qr_code(client, monkeypatch, listening):
    monkeypatch.setattr(connect, "lan_address", lambda: "192.168.1.50")
    monkeypatch.setattr(connect, "port_open", lambda address, port: listening and (address, port) == ("192.168.1.50", 80))
    assert client.get("/api/connect").json() == {"url": "http://192.168.1.50:80/", "reachable": listening}
    qr = client.get("/api/connect/qr.svg")
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/svg+xml"
    assert qr.text.lstrip().startswith("<?xml") and "<svg" in qr.text


def test_connect_without_network(client, monkeypatch):
    monkeypatch.setattr(connect, "lan_address", lambda: None)
    assert client.get("/api/connect").json() == {"url": None, "reachable": False}
    assert client.get("/api/connect/qr.svg").status_code == 404


def test_real_mode_requires_a_device_token():
    with pytest.raises(ValueError, match="FLORABOT_DEVICE_TOKEN"):
        Settings(device_mode="real", device_token="short")
    assert Settings(device_mode="dummy", device_token=None).device_token is None


@pytest.mark.parametrize(
    ("route", "interfaces", "expected"),
    [
        # Work laptop on VPN: the default route is the tunnel, Wi-Fi is en0, plus VM bridges.
        ("17.233.81.87", {"lo0": ["127.0.0.1"], "en0": ["192.168.1.5"], "bridge100": ["192.168.139.3"], "utun6": ["17.233.81.87"]}, "192.168.1.5"),
        ("192.168.0.20", {"en0": ["192.168.0.20"], "en1": ["10.0.0.7"]}, "192.168.0.20"),
        ("10.8.0.2", {"utun3": ["10.8.0.2"], "wlan0": ["192.168.4.9"]}, "192.168.4.9"),
        (None, {"bridge100": ["192.168.64.1"]}, "192.168.64.1"),
        (None, {"lo0": ["127.0.0.1"], "en0": ["169.254.10.10"], "utun6": ["17.1.2.3"]}, None),
    ],
)
def test_pick_lan_address(route, interfaces, expected):
    assert connect.pick_lan_address(route, interfaces) == expected


def test_port_open_detects_a_listening_socket():
    import socket

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert connect.port_open("127.0.0.1", port)
    assert not connect.port_open("127.0.0.1", port)
