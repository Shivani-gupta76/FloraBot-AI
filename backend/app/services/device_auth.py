"""Cryptographic helpers for high-entropy device credentials."""
import hashlib
import hmac
import secrets


_DUMMY_CREDENTIAL_HASH = "0" * 64


def generate_device_token() -> str:
    """Generate a 256-bit URL-safe credential for one-time provisioning."""
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    """Return the SHA-256 verifier for a high-entropy random token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_device_token(token: str, stored_hash: str | None) -> bool:
    """Compare fixed-length token verifiers without data-dependent string comparison."""
    candidate_hash = hash_device_token(token)
    expected_hash = stored_hash if stored_hash is not None and len(stored_hash) == 64 else _DUMMY_CREDENTIAL_HASH
    matches = hmac.compare_digest(candidate_hash, expected_hash)
    return stored_hash is not None and len(stored_hash) == 64 and matches
