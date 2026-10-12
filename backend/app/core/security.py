from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from pwdlib import PasswordHash
from app.core.config import settings

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(subject: str) -> str:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be configured before issuing tokens")
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": subject, "exp": expires}, settings.secret_key, algorithm=ALGORITHM)


def decode_subject(token: str) -> str:
    if not settings.secret_key:
        raise JWTError("Token signing is not configured")
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise JWTError("Invalid token subject")
    return subject
