"""The handshake rejection reaches the client as a bare HTTP 403, so the server
log is the only place the actual cause is visible — it has to be specific."""

from datetime import datetime, timedelta, timezone

import jwt

from backend.api.websocket import _rejection_reason

SECRET = "a-secret-long-enough-for-hs256-0123456789"


def _token(**overrides) -> str:
    payload = {
        "sub": "user",
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    payload.update(overrides)
    return jwt.encode(payload, overrides.pop("secret", SECRET), algorithm="HS256")


def test_an_expired_token_is_reported_as_expired():
    expired = _token(
        iat=datetime.now(timezone.utc) - timedelta(hours=1),
        exp=datetime.now(timezone.utc) - timedelta(minutes=45),
    )
    assert _rejection_reason(expired, SECRET) == "token expired"


def test_a_token_signed_with_another_secret_is_reported_as_such():
    foreign = jwt.encode(
        {"sub": "user", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "a-different-secret-0123456789abcdefghij",
        algorithm="HS256",
    )
    assert "JWT_SECRET" in _rejection_reason(foreign, SECRET)


def test_a_valid_but_wrong_type_token_is_reported_as_wrong_type():
    refresh = _token(type="refresh")
    assert "wrong token type" in _rejection_reason(refresh, SECRET)
