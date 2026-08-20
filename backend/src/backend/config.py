from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads the repo-root .env whether the server is started from the repo root
    # or from backend/ (later entries win).
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://investor:investor@localhost:5432/investor"

    @field_validator("database_url")
    @classmethod
    def _force_psycopg_driver(cls, value: str) -> str:
        # .env uses the plain postgresql:// scheme; SQLAlchemy needs the psycopg3 driver spelled out.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_refresh_secret: str = "dev-only-refresh-secret-change-me"
    app_password_hash: str = ""
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 7 * 24 * 60 * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
