# portfolio-tracker

Personal, single-user investment tracking app, inspired by Investidor10. Full documentation in [`docs/`](docs/architecture.md).

## Structure

```
backend/     # Python + FastAPI + uv — business logic, REST API, background jobs
  src/backend/
    domain/          # pure business rules (average price, rebalancing, indicators, corporate actions...)
    application/     # use cases (recalculation, B3 import, snapshots, catch-up)
    ports/           # interfaces the infrastructure implements
    infrastructure/  # Postgres, brapi.dev, B3 parser, scheduled jobs
    api/             # FastAPI app, routes and the WebSocket channel
  migrations/        # Alembic
  tests/
frontend/    # Tauri + React + Vite — desktop app
  src/         # React UI (dashboard, login)
  src-tauri/   # native Rust shell (capabilities, per-OS build)
  e2e/         # Playwright
docs/
  architecture.md
  business-rules.md
  sprints.md
  testing-strategy.md
  openapi/openapi.yaml
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager, also installs the right Python version for you
- [Node.js](https://nodejs.org) 20+ and npm — for the frontend
- [Docker](https://docker.com) (Postgres + Redis) — required by `backend/`
- [Rust + Cargo](https://www.rust-lang.org/tools/install) — required to build the desktop app (Tauri)
- On Linux, Tauri's system dependencies: see [tauri.app/start/prerequisites](https://tauri.app/start/prerequisites/)

## Setup

```bash
cp .env.example .env
docker compose up -d

cd backend && uv sync
uv run alembic upgrade head                  # apply database migrations
uv run python -m backend.cli hash-password   # generate APP_PASSWORD_HASH for .env
```

## Tests

Unit tests (`backend/tests/domain`) are pure and need no database; integration tests (`backend/tests/integration`) need Postgres up (they use `TEST_DATABASE_URL`, defaulting to an `investor_test` database on the docker-compose instance — create it once with `docker compose exec postgres createdb -U investor investor_test`):

```bash
cd backend && uv run pytest tests/domain   # fast, no Docker
cd backend && uv run pytest                # everything
```

## Running locally

```bash
# backend (http://localhost:8000, interactive docs at /docs)
cd backend && uv run uvicorn backend.api.app:app --reload
```

```bash
# app in the browser — fastest loop, no Rust needed (http://localhost:1420)
cd frontend && npm install && npm run dev
```

```bash
# native desktop window (needs Rust + Cargo installed)
cd frontend && npm run tauri dev
```

See [frontend/README.md](frontend/README.md) for the API client generation and E2E tests.
