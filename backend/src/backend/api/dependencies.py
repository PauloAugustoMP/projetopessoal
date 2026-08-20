from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.api.errors import ApiError
from backend.api.security import decode_token
from backend.config import Settings, get_settings
from backend.infrastructure.persistence.database import get_session

_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: SettingsDep,
) -> None:
    if credentials is None or decode_token(credentials.credentials, settings.jwt_secret, "access") is None:
        raise ApiError(401, "UNAUTHORIZED", "Missing or invalid access token.")
