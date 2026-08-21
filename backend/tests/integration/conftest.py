"""Integration-test setup: real Postgres (TEST_DATABASE_URL, defaults to the
docker-compose instance's `investor_test` database), schema applied through the
actual Alembic migrations, tables truncated between tests."""

import os
from pathlib import Path

import pytest

TEST_PASSWORD = "test-password"

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://investor:investor@localhost:5432/investor_test"
)
os.environ["JWT_SECRET"] = "integration-test-secret-0123456789abcdef"
os.environ["JWT_REFRESH_SECRET"] = "integration-test-refresh-secret-0123456789abcdef"
os.environ["ENABLE_JOBS"] = "false"  # no scheduler/catch-up/network in tests

from backend.api.security import hash_password  # noqa: E402

os.environ["APP_PASSWORD_HASH"] = hash_password(TEST_PASSWORD)

from backend.config import get_settings  # noqa: E402

get_settings.cache_clear()

from sqlalchemy import text  # noqa: E402

from backend.infrastructure.persistence.database import get_engine, reset_engine  # noqa: E402

reset_engine()

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    from alembic import command
    from alembic.config import Config

    with get_engine().begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def seeded_tickers(migrated_database) -> list[str]:
    """The catalog shipped by the migration — everything else is test residue."""
    with get_engine().begin() as connection:
        return [row[0] for row in connection.execute(text("SELECT ticker FROM assets"))]


@pytest.fixture(autouse=True)
def clean_tables(seeded_tickers):
    yield
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "TRUNCATE transactions, positions, dividends, corporate_actions, "
                "import_review_rows, portfolio_snapshots, price_history, system_state"
            )
        )
        # Imports register assets on the fly; drop those so the next test starts
        # from the same catalog.
        connection.execute(
            text("DELETE FROM assets WHERE ticker <> ALL(:seeded)"),
            {"seeded": seeded_tickers},
        )


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from backend.api.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}
