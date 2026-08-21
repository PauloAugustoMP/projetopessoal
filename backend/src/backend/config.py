from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads the repo-root .env whether the server is started from the repo root
    # or from backend/ (later entries win).
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://investor:investor@localhost:5432/investor"
    redis_url: str = "redis://localhost:6379"

    jwt_secret: str = "dev-only-secret-change-me"
    jwt_refresh_secret: str = "dev-only-refresh-secret-change-me"
    app_password_hash: str = ""
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 7 * 24 * 60 * 60

    # Origins allowed to call the API from a browser context: the Vite dev server
    # and the Tauri webview (docs/architecture.md §5 — nothing is exposed publicly).
    cors_allowed_origins: tuple[str, ...] = (
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
    )

    brapi_api_token: str = ""
    quote_cache_ttl_seconds: int = 30

    # Scheduled jobs + startup catch-up (disabled in tests so nothing hits the network).
    enable_jobs: bool = True
    price_poll_interval_seconds: int = 30
    daily_snapshot_hour: int = 18  # after B3 close, Brasília time

    @field_validator("database_url")
    @classmethod
    def _force_psycopg_driver(cls, value: str) -> str:
        # .env uses the plain postgresql:// scheme; SQLAlchemy needs the psycopg3 driver spelled out.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
