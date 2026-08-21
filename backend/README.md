# Backend — Investment Tracker API

FastAPI backend for the personal investment tracking app. Managed with
[uv](https://docs.astral.sh/uv/). Layering and dependency rules in
[docs/architecture.md](../docs/architecture.md) §3.

## Setup

```bash
uv sync                      # install dependencies
cp ../.env.example ../.env   # then fill in the secrets
uv run alembic upgrade head  # apply database migrations (Postgres must be up)
uv run uvicorn backend.api.app:app --reload
```

Interactive API docs at http://localhost:8000/docs.

## Configuration

Settings come from the repo-root `.env` ([config.py](src/backend/config.py)), which is read
whether the server starts from the repo root or from `backend/`.

| Variable | Effect when unset |
|---|---|
| `DATABASE_URL` | defaults to the docker-compose Postgres |
| `APP_PASSWORD_HASH` | every login is rejected |
| `JWT_SECRET` / `JWT_REFRESH_SECRET` | insecure development defaults — set them |
| `BRAPI_API_TOKEN` | quotes, price history and logos are disabled; the app falls back to cost basis and `price_poll` is not scheduled |
| `REDIS_URL` | quote cache degrades to an in-process dict |
| `ENABLE_JOBS` | `true`; set `false` to start without the scheduler or the startup catch-up |

`APP_PASSWORD_HASH` contains `$` characters, so quote it with **single** quotes in `.env` —
otherwise Docker Compose tries to expand them as variables.

## Commands

```bash
uv run python -m backend.cli hash-password              # generate APP_PASSWORD_HASH
uv run python -m backend.cli inspect-statement <file>   # diagnose a B3 export
```

`inspect-statement` prints only an export's structure — header labels and cell counts,
never row values — so an unrecognized layout can be shared without exposing financial data.

## Migrations

```bash
uv run alembic upgrade head                                  # apply
uv run alembic revision --autogenerate -m "what changed"     # create from model changes
```

Always read the generated revision before committing it; autogenerate does not detect
everything, and the initial migration also seeds a starter asset catalog.

## Tests

```bash
uv run pytest tests/domain tests/b3_import tests/market_data tests/api   # no database needed
uv run pytest tests/integration                                          # needs Postgres
uv run pytest                                                            # everything
```

Integration tests use `TEST_DATABASE_URL` (defaults to `investor_test` on the compose
instance) and apply the real migrations. Create the database once:

```bash
docker compose exec postgres createdb -U investor investor_test
```

No test touches the network: the market data provider is replaced by a fake, and the
adapter's contract tests run against recorded JSON. See
[docs/testing-strategy.md](../docs/testing-strategy.md).
