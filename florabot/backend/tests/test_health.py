import json

import pytest

from app.analysis import finish_interrupted_analyses
from app.config import get_settings
from app.db import SessionLocal
from app.decision import Recommendation
from app.deps import get_classifier, get_provider
from app.disease import LEAF_MODEL_LABELS, DiseasePrediction, YoloClassifier, describe, readable
from app.main import app
from app.models import Analysis, HealthCheck, HealthStatus
from app.vision.mock import MockProvider
from tests.conftest import image_bytes

WHITEFLY_REVIEW = {
    "plant": "Tomato",
    "finding": "PEST",
    "problem": "Whiteflies",
    "possible_causes": [],
    "confidence_level": "MEDIUM",
    "agrees_with_leaf_model": False,
    "observations": ["Small white insects on the leaves."],
    "advice": "Check the undersides of the leaves and ask a local nursery about control.",
}


class Reviewer(MockProvider):
    """Watering comes from the mock; the health review is scripted and records what it was given."""

    name = "reviewer"

    def __init__(self, reply="", error=None, on_review=None):
        super().__init__(Recommendation.WATERING_NOT_RECOMMENDED)
        self.reply, self.error, self.on_review, self.contexts = reply, error, on_review, []

    def review_health(self, image, mime_type, leaf_model, model=None):
        self.contexts.append(leaf_model)
        if self.on_review:
            self.on_review()
        if self.error:
            raise self.error
        return self.reply


class FixedClassifier:
    name = "fixed"
    labels = LEAF_MODEL_LABELS

    def __init__(self, prediction=None, error=None):
        self.prediction, self.error = prediction, error

    def classify(self, image):
        if self.error:
            raise self.error
        return self.prediction


def analyze(client) -> dict:
    created = client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")}).json()
    return client.get(f"/api/analyses/{created['analysis_id']}").json()


def test_initial_assessment_then_ai_review(client):
    health = analyze(client)["health"]
    assert health["status"] == "DONE"
    assert health["initial"] == {
        "crop": "Tomato",
        "condition": "Healthy",
        "healthy": True,
        "confidence_level": "HIGH",
        "confident": True,
        "message": "This looks like a healthy tomato leaf.",
        "alternatives": ["Tomato · Leaf mold", "Tomato · Early blight"],
    }
    assert health["review"]["finding"] == "HEALTHY"


def test_initial_assessment_is_saved_before_the_review_runs(client):
    seen = {}

    def capture():
        with SessionLocal() as db:
            check = db.query(HealthCheck).one()
            seen.update(status=check.status, label=check.leaf_label, review=check.review)

    reviewer = Reviewer(reply=json.dumps(WHITEFLY_REVIEW), on_review=capture)
    app.dependency_overrides[get_provider] = lambda: reviewer
    health = analyze(client)["health"]
    assert seen == {"status": HealthStatus.REVIEWING, "label": "Tomato_Healthy", "review": None}
    assert (health["review"]["finding"], health["review"]["problem"]) == ("PEST", "Whiteflies")


def test_review_gets_the_leaf_models_full_context(client):
    reviewer = Reviewer(reply=json.dumps(WHITEFLY_REVIEW))
    app.dependency_overrides[get_provider] = lambda: reviewer
    analyze(client)
    context = reviewer.contexts[0]
    assert "Tomato · Healthy 93%" in context and "Tomato · Leaf mold 4%" in context
    assert all(" · ".join(readable(label)) in context for label in LEAF_MODEL_LABELS)


@pytest.mark.parametrize(
    "reviewer",
    [Reviewer(error=TimeoutError("slow")), Reviewer(reply="not json"), Reviewer(reply='{"plant": "Tomato"}')],
    ids=["error", "not-json", "incomplete"],
)
def test_failed_review_is_reported_and_the_initial_assessment_stays(client, reviewer):
    app.dependency_overrides[get_provider] = lambda: reviewer
    analysis = analyze(client)
    health = analysis["health"]
    assert (health["status"], health["review"]) == ("REVIEW_UNAVAILABLE", None)
    assert health["initial"]["message"] == "This looks like a healthy tomato leaf."
    assert analysis["recommendation"] == "WATERING_NOT_RECOMMENDED"


def test_review_still_runs_when_the_leaf_model_fails(client):
    reviewer = Reviewer(reply=json.dumps(WHITEFLY_REVIEW))
    app.dependency_overrides[get_provider] = lambda: reviewer
    app.dependency_overrides[get_classifier] = lambda: FixedClassifier(error=RuntimeError("model crashed"))
    health = analyze(client)["health"]
    assert (health["status"], health["initial"]) == ("DONE", None)
    assert reviewer.contexts == ["The leaf model could not check this photo."]


@pytest.mark.parametrize(
    ("label", "confidence", "level", "message"),
    [
        ("Tomato_Late_Blight", 0.91, "HIGH", "This looks most like late blight on a tomato leaf."),
        ("Potato_Early_Blight", 0.62, "MEDIUM", "This might be early blight on a potato leaf, but I'm not certain."),
        ("Pepper_Healthy", 0.55, "MEDIUM", "This might be a healthy pepper leaf, but I'm not certain."),
        ("Tomato_Leaf_Mold", 0.31, "LOW", "I couldn't recognize this leaf."),
    ],
)
def test_initial_assessment_is_worded_by_confidence(client, label, confidence, level, message):
    prediction = DiseasePrediction(label, confidence, ["Tomato_Healthy"], ((label, confidence),))
    app.dependency_overrides[get_classifier] = lambda: FixedClassifier(prediction)
    initial = analyze(client)["health"]["initial"]
    assert (initial["confidence_level"], initial["message"], initial["confident"]) == (level, message, level == "HIGH")


def test_health_check_never_creates_an_led_command(client):
    app.dependency_overrides[get_provider] = lambda: MockProvider(Recommendation.UNCERTAIN)
    assert analyze(client)["health"]["status"] == "DONE"
    assert client.get("/api/hardware/commands").json() == []


def test_restart_closes_unfinished_health_checks(client):
    with SessionLocal() as db:
        db.add(Analysis(id="cut-off", provider="mock", health=HealthCheck(status=HealthStatus.REVIEWING, leaf_label="Tomato_Healthy", leaf_confidence=0.9)))
        db.commit()
    finish_interrupted_analyses()
    health = client.get("/api/analyses/cut-off").json()["health"]
    assert health["status"] == "REVIEW_UNAVAILABLE"
    assert health["initial"]["crop"] == "Tomato"


def test_readable_labels():
    assert readable("Tomato_Yellow_Leaf_Curl_Virus") == ("Tomato", "Yellow leaf curl virus")
    assert readable("Pepper_Healthy") == ("Pepper", "Healthy")
    assert describe(DiseasePrediction("Tomato_Spider_Mites", 0.85, [])) == "This looks most like spider mites on a tomato leaf."


def test_the_trained_model_loads_and_classifies():
    classifier = YoloClassifier(get_settings().disease_model_path)
    prediction = classifier.classify(image_bytes("PNG", (640, 480)))
    assert prediction.label in LEAF_MODEL_LABELS
    assert 0 <= prediction.confidence <= 1
    assert len(prediction.alternatives) == 2 and set(prediction.alternatives) <= set(LEAF_MODEL_LABELS)
    assert len(prediction.scores) == 5 and prediction.scores[0][0] == prediction.label
    assert set(classifier.labels) == set(LEAF_MODEL_LABELS)


def test_unclear_sign_comes_with_possible_causes(client):
    unclear = {
        **WHITEFLY_REVIEW,
        "finding": "UNCLEAR",
        "problem": "White specks on leaves",
        "possible_causes": ["Shed insect skins", "Whiteflies", "Dust or perlite"],
        "advice": "Tap the leaves: whiteflies fly up, shed skins and dust do not.",
    }
    app.dependency_overrides[get_provider] = lambda: Reviewer(reply=json.dumps(unclear))
    review = analyze(client)["health"]["review"]
    assert (review["finding"], review["problem"]) == ("UNCLEAR", "White specks on leaves")
    assert review["possible_causes"] == ["Shed insect skins", "Whiteflies", "Dust or perlite"]


def test_review_prompt_asks_for_evidence_before_naming_a_pest():
    from app.vision.prompt import HEALTH_REVIEW_PROMPT

    assert "Only name a pest when" in HEALTH_REVIEW_PROMPT and "possible_causes" in HEALTH_REVIEW_PROMPT
    assert "Use HIGH only when the signs are unmistakable" in HEALTH_REVIEW_PROMPT
