# portfolio-tracker

Personal, single-user investment tracking app, inspired by Investidor10. Runs entirely on
your own machine — no public port, no cloud. Full documentation in [`docs/`](docs/architecture.md).

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
data/        # Postgres + Redis files (bind-mounted by docker compose, gitignored)
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
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs Postgres and Redis
- [Rust + Cargo](https://www.rust-lang.org/tools/install) — **only** to build the native desktop window; the app runs in the browser without it

---

## First-time setup

Do this once. The day-to-day flow is the next section.

**1. Create your `.env` from the template**

```bash
cp .env.example .env
```

**2. Generate the two JWT secrets**

```bash
python3 -c "import secrets; print(secrets.token_hex(32)); print(secrets.token_hex(32))"
```

Paste the two values into `JWT_SECRET` and `JWT_REFRESH_SECRET` in `.env`.

**3. Set your app password**

The app has a single password (single-user auth, [architecture §5](docs/architecture.md#5-security)).
This command asks for it without echoing it and prints its argon2 hash:

```bash
cd backend && uv run python -m backend.cli hash-password
```

Paste the hash into `APP_PASSWORD_HASH` in `.env`, **between single quotes**:

```
APP_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$...'
```

> The single quotes matter: the hash contains `$`, and Docker Compose would otherwise try
> to expand them as variables. Only the hash is stored — the password itself never is, so
> it cannot be recovered. Forgot it? Just run the command again and set a new one.

**4. Start the database and install dependencies**

```bash
docker compose up -d
```

```bash
cd backend && uv sync && uv run alembic upgrade head
```

```bash
cd frontend && npm install
```

**5. (Optional) Quotes**

Live prices come from [brapi.dev](https://brapi.dev). Without a token in `BRAPI_API_TOKEN`,
the app still works — it falls back to your average cost and shows `—` where a quote
would go. That degradation is deliberate, not an error.

---

## Running the app

Three steps, two terminals.

**1. Database** — once per session (with Docker Desktop set to open at login, it comes up on its own):

```bash
docker compose up -d
```

**2. Backend** — terminal 1, leave it open:

```bash
cd backend && uv run uvicorn backend.api.app:app --reload
```

Wait for `Application startup complete`. The API is at `http://localhost:8000`, with
interactive docs at **http://localhost:8000/docs**.

**3. Frontend** — terminal 2, leave it open:

```bash
cd frontend && npm run dev
```

Open **http://localhost:1420** and log in with your password.

### Native desktop window

Needs Rust installed. Same backend, just a native shell instead of the browser tab:

```bash
cd frontend && npm run tauri dev
```

### Stopping

`Ctrl+C` in both terminals. The containers keep running harmlessly; to stop them too:

```bash
docker compose down
```

This does **not** delete your data — it lives in `data/postgres/`.

---

## Troubleshooting

**`ERROR: [Errno 48] Address already in use`** — an older backend is still holding port 8000:

```bash
lsof -ti:8000 | xargs kill -9
```

**Database connection errors** — check the containers are healthy:

```bash
docker compose ps
```

**Quotes show as `—`** — expected while `BRAPI_API_TOKEN` is empty (see step 5 above).

**Login returns 401** — the `APP_PASSWORD_HASH` in `.env` doesn't match the password you
typed, or the backend was started before you saved `.env`. Restart the backend after editing it.

---

## Entering data

The dashboard is read-only for now — the screens for entering transactions and importing
statements land in the next sprints ([docs/sprints.md](docs/sprints.md)). Until then, use the
interactive docs at `http://localhost:8000/docs`:

1. `POST /api/auth/login` with your password → copy the `accessToken`
2. Click **Authorize** and paste it
3. `POST /api/transactions` to record a buy or sell, or `POST /api/import/b3-statement`
   to upload your B3 statement (see below)

### Importing a B3 statement

Download it yourself from the B3 investor portal — the app never touches your B3 login
([architecture §5](docs/architecture.md#5-security), a deliberate decision):

1. Log in at [investidor.b3.com.br](https://www.investidor.b3.com.br)
2. **Extratos → Movimentação**, pick the date range
3. Download as Excel or CSV — keep the file exactly as exported

Then upload it. Via `/docs`, use `POST /api/import/b3-statement` and pick the file; or from
the terminal:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'content-type: application/json' -d '{"password":"YOUR_PASSWORD"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
```

```bash
curl -s -X POST http://localhost:8000/api/import/b3-statement \
  -H "authorization: Bearer $TOKEN" -F "file=@/path/to/movimentacao.xlsx" \
  | python3 -m json.tool
```

The response reports what happened:

```json
{
  "transactionsCreated": 12,
  "dividendsCreated": 5,
  "corporateActionsCreated": 1,
  "duplicatesSkipped": 3,
  "rowsForManualReview": [{ "row": 18, "reason": "Unrecognized movement type: ..." }]
}
```

Re-importing the same file is safe: rows already recorded are matched on ticker + date +
quantity + price and counted as `duplicatesSkipped`, never duplicated — including entries you
had typed in by hand ([business-rules §7](docs/business-rules.md#7-b3-statement-import)).
Anything the parser can't decide on its own lands in `rowsForManualReview` instead of failing
the import.

Recognized movements: `Transferência - Liquidação` (buys and sells), `Dividendo`,
`Juros Sobre Capital Próprio`, `Rendimento`, `Desdobro`, `Grupamento`,
`Bonificação em Ativos`, and exercised subscription rights. Purely informational rows
(such as `Atualização`) are skipped silently.

---

## Tests

```bash
cd backend && uv run pytest tests/domain   # unit — pure, no database needed
cd backend && uv run pytest                # everything (needs Postgres up)
```

Integration tests use `TEST_DATABASE_URL`, defaulting to an `investor_test` database on the
compose instance. Create it once:

```bash
docker compose exec postgres createdb -U investor investor_test
```

End-to-end tests (Playwright, needs the backend running) live in the frontend:

```bash
cd frontend && npm run test:e2e
```

See [docs/testing-strategy.md](docs/testing-strategy.md) for the full strategy, and
[frontend/README.md](frontend/README.md) for API client generation.

---

## Your data

Postgres and Redis files are bind-mounted into `./data` rather than living inside a Docker
named volume, so they stay visible on the host — which keeps the scheduled `pg_dump` backup
(Sprint 7) and manual inspection straightforward. The folder is gitignored; never commit it.

`.env` holds your secrets and is gitignored too.
