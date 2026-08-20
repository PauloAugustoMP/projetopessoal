# Backend — Investment Tracker API

FastAPI backend for the personal investment tracking app. Managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
uv sync                      # install dependencies
cp ../.env.example ../.env   # then fill in the secrets
uv run alembic upgrade head  # apply database migrations (Postgres must be up)
uv run uvicorn backend.api.app:app --reload
```

Generate the single-user password hash for `APP_PASSWORD_HASH`:

```bash
uv run python -m backend.cli hash-password
```

## Tests

```bash
uv run pytest tests/domain        # unit tests (no database needed)
uv run pytest tests/integration   # needs Postgres (TEST_DATABASE_URL, defaults to the docker-compose instance)
uv run pytest                     # everything
```

See [docs/architecture.md](../docs/architecture.md) and [docs/testing-strategy.md](../docs/testing-strategy.md).
