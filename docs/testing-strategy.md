# Testing strategy

## Pyramid

```
                    ▲
                   /E2E\             4 — golden paths in the app (Playwright)
                  /------\
                 /Integration\      56 — backend against a real Postgres
                /------------\
               / Contract/adapter\    8 — quote provider, recorded responses
              /--------------------\
             /        Unit            \  98 — pure rules, statement parser, helpers
            /--------------------------\
```

162 backend tests (98 unit + 8 contract + 56 integration) and 4 E2E, all passing. The
counts are indicative, not targets — they are here so drift between this document and the
suite is visible.

General rule: if a business rule can be tested without a database and without the network, it **must** be tested in `backend/src/backend/domain`, not implicitly through an integration test alone. This keeps the suite fast (runs in milliseconds, no Docker needed) and the integration tests lean (they only verify the wiring, not the logic itself).

## 1. Unit tests — `backend/src/backend/domain`

- **Tool**: pytest.
- **Expected coverage**: high (target ≥ 90% of lines) — it's pure logic, no excuse not to test it.
- **What to cover**: every case listed in [business-rules.md](business-rules.md), especially the edge cases already flagged in the document (position hitting zero, sell larger than the position, every asset already above target, negative EPS/book value, app closed for weeks, etc).
- **Where they live**: `backend/tests/domain/` mirrors `src/backend/domain/`, one file per module (66 tests). The B3 statement parser is pure too — no database, no network — so it is tested the same way under `backend/tests/b3_import/` (28 tests, with anonymized sample files). `backend/tests/api/` holds the few API helpers that are pure enough to test directly (4 tests).
- **Convention**: a `test_*.py` file per module, mirrored under `backend/tests/domain/`. Test names describe the behavior in plain English, not the implementation (`test_does_not_change_the_average_price_on_a_sell`, not `test_apply_sell_function`).
- **Never mock inside the domain layer** — if a domain test "needs" a mock, that's a sign the piece belongs in infrastructure, not domain.

## 2. Integration tests — `backend`

- **Tool**: pytest + FastAPI's `TestClient` against a real Postgres running in a container (the same `docker-compose.yml`, a separate test database — `investor_test`, created once with `docker compose exec postgres createdb -U investor investor_test`).
- **Schema comes from the real migrations**: the session fixture drops and recreates the schema, then runs `alembic upgrade head`. A migration that does not apply cleanly fails the suite, not production.
- **What to cover**:
  - Transaction CRUD and the recalculation engine running end to end against the database (not just the domain's pure function — here what matters is that the background task actually runs and persists).
  - B3 statement import: upload → parse → dedup → save, with sample files under `backend/tests/fixtures/`.
  - Startup snapshot catch-up: simulate a past `last_snapshot_date`, start the module, confirm the missing snapshots were created.
  - Authentication and authorization (protected routes rejecting a request without a token; the WebSocket rejecting an expired, foreign-signed or wrong-type token).
  - Payload validation (Pydantic) returning 400s in the shape expected by `openapi.yaml`.
  - CORS: the app's own origins allowed, unknown origins not.
  - **Running without a market data token** — a supported state. The dashboard must answer 200 with prices null, and `price_poll` must not be scheduled.
- **Isolation**: tables are truncated after every test. The catalog needs care: imports register assets on the fly, so the fixture captures the tickers seeded by the migration and deletes anything else — without that, import tests grow progressively less meaningful as the suite expands.
- **No external network**: the quote provider is replaced by the mock from section 3 — integration tests must not depend on brapi.dev being up.

## 3. Contract / adapter tests

- **What it is**: tests for `brapi_provider.py` against **recorded** responses (real JSON fixtures, captured once and checked into the repo), not against the live API. The provider's official SDK accepts an injected `httpx` client, so the adapter is exercised end to end with a mock transport — we test the real response shape, not the SDK's own mocks.
- **Why**: proves the adapter correctly parses the provider's real response shape, without making the suite depend on the network or get rate-limited.
- **What to cover**: field mapping (including a missing `logourl` → the fallback handled in another layer); every provider failure — rate limit, connection error, HTTP status, and a 200 carrying an unexpected payload — surfacing as `MarketDataUnavailableError` rather than a generic exception; a historical series with missing days (holiday/weekend); an unknown ticker being absent from the result instead of an error.
- **Updating fixtures**: when the provider changes its response shape, recapture manually and check the new fixture in — don't automate the capture as part of CI.

## 4. E2E tests — desktop app

- **Tool**: Playwright, pointed at the Tauri build's webview (Tauri exposes it via WebDriver for `tauri dev`; alternatively, the same Vite/React frontend can be run directly in a browser for faster tests, since the UI logic doesn't depend on the native shell — only OS-specific features, like the file picker dialog, require the actual Tauri binary).
- **Covered today** (`frontend/e2e/login.spec.ts`): login → dashboard with real data; wrong password; the dashboard unreachable while logged out; logout. These run against a live backend and a real Postgres — it was this suite that surfaced the missing CORS configuration.
- **Golden paths still to cover** (one test per flow, not per screen):
  1. Login → dashboard loads with real data. ✅
  2. Enter a transaction (buy) → position and total value update on screen.
  3. Enter a backdated transaction → confirm the dashboard reflects the recalculation (tolerating the "recalculating..." state before the final result).
  4. Import a B3 statement → import summary shown, positions updated.
  5. Define an allocation target → simulate a contribution → see a suggestion consistent with the target.
  6. Reinvest the dividend balance → balance resets to zero, suggested purchases appear.
  7. Open an indicator's tooltip → explanatory text visible.
- **Out of scope for E2E**: business-rule variations (already exhaustively covered by the domain's unit tests) — E2E only proves the right screen shows the right data.

## 5. Test data

- Simple factories in `backend/tests/factories.py` (reused by integration tests) to build payloads with sensible defaults and targeted overrides — avoids tests cluttered with hand-built giant objects.
- `backend/tests/fakes.py` holds `FakeMarketDataProvider`, injected through `set_market_data_provider` so no integration test touches the network.
- B3 statement fixtures (`backend/tests/fixtures/*.csv`), anonymized — never check in one of your own real statements. When a real export breaks the parser, add a fixture reproducing **its layout** with invented values.
- Recorded provider responses (`backend/tests/fixtures/brapi_*.json`) for the contract tests.

## 6. What each sprint delivers in tests

See [sprints.md](sprints.md) — every sprint has its own "Definition of done" with the corresponding tests; there's no separate "test everything at the end" phase. The suite grows together with the feature.

## 7. Running the suite

```bash
# unit + contract (fast, no Docker needed)
cd backend && uv run pytest tests/domain tests/b3_import tests/market_data tests/api

# integration (needs docker compose up, and the investor_test database)
cd backend && uv run pytest tests/integration

# everything in the backend
cd backend && uv run pytest

# E2E (needs the backend running; E2E_PASSWORD must match your .env)
cd frontend && npm run test:e2e
```

The integration suite points at `TEST_DATABASE_URL`, defaulting to `investor_test` on the
compose instance. Create it once:

```bash
docker compose exec postgres createdb -U investor investor_test
```

## 8. What we deliberately don't test

- The exact behavior of third-party libraries (FastAPI, SQLAlchemy, Tauri) — we trust their contract.
- The accuracy of the external provider's quotes — we validate that we *use* the returned data correctly, not that the data itself is correct (that's the provider's responsibility).
- Load/performance — out of scope for single-user usage.
- The provider SDK's own behaviour — we test that our adapter maps real recorded responses correctly, not that the SDK parses them.
