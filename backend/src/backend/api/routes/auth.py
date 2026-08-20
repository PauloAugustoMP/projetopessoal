from fastapi import APIRouter

from backend.api.dependencies import SettingsDep
from backend.api.errors import ApiError
from backend.api.schemas import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse
from backend.api.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse, response_model_by_alias=True)
def login(body: LoginRequest, settings: SettingsDep) -> LoginResponse:
    if not settings.app_password_hash or not verify_password(
        body.password, settings.app_password_hash
    ):
        raise ApiError(401, "UNAUTHORIZED", "Invalid password.")
    return LoginResponse(
        access_token=create_access_token(settings),
        refresh_token=create_refresh_token(settings),
    )


@router.post("/refresh", response_model=RefreshResponse, response_model_by_alias=True)
def refresh(body: RefreshRequest, settings: SettingsDep) -> RefreshResponse:
    if decode_token(body.refresh_token, settings.jwt_refresh_secret, "refresh") is None:
        raise ApiError(401, "UNAUTHORIZED", "Invalid or expired refresh token.")
    return RefreshResponse(access_token=create_access_token(settings))
