import pytest

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "sqlite://",
        "environment": "production",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_missing_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="^Production requires a non-placeholder SECRET_KEY with at least 32 characters\\.$"):
        _settings()


@pytest.mark.parametrize("secret_key", ["", " \t\r\n", "short"])
def test_production_rejects_blank_or_short_secret_key(secret_key):
    with pytest.raises(ValueError, match="^Production requires a non-placeholder SECRET_KEY with at least 32 characters\\.$"):
        _settings(secret_key=secret_key)


def test_production_rejects_obvious_placeholder_secret():
    with pytest.raises(ValueError, match="^Production requires a non-placeholder SECRET_KEY with at least 32 characters\\.$"):
        _settings(secret_key="please-change-me-before-production-123456")


def test_production_accepts_long_non_placeholder_secret_case_insensitively():
    configured = _settings(
        environment="PrOdUcTiOn",
        secret_key="0123456789abcdefABCDEF!@#xyz987654321",
    )

    assert configured.environment == "PrOdUcTiOn"


def test_development_keeps_empty_secret_compatibility():
    configured = _settings(environment="development", secret_key="")

    assert configured.secret_key == ""


def test_valid_production_secret_still_signs_and_verifies_jwt(monkeypatch):
    from app.core import security

    configured_secret = "0123456789abcdefABCDEF!@#xyz987654321"
    _settings(secret_key=configured_secret)
    monkeypatch.setattr(security.settings, "secret_key", configured_secret)

    token = security.create_access_token("test-subject")

    assert security.decode_subject(token) == "test-subject"
