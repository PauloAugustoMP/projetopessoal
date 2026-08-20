from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from backend.config import Settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed hash (e.g. APP_PASSWORD_HASH not configured) — treat as invalid.
        return False


def _create_token(secret: str, token_type: str, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user",
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_access_token(settings: Settings) -> str:
    return _create_token(settings.jwt_secret, "access", settings.access_token_ttl_seconds)


def create_refresh_token(settings: Settings) -> str:
    return _create_token(
        settings.jwt_refresh_secret, "refresh", settings.refresh_token_ttl_seconds
    )


def decode_token(token: str, secret: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
