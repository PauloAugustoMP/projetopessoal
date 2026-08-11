# Testing strategy

## Pyramid

```
                    ▲
                   /E2E\          few — golden paths in the desktop app (Playwright)
                  /------\
                 /Integration\    moderate — backend against a real Postgres
                /------------\
               / Contract/adapter\  few — quote provider mocks
              /--------------------\
             /        Unit            \  many — backend/src/backend/domain, no I/O
            /--------------------------\
```

General rule: if a business rule can be tested without a database and without the network, it **must** be tested in `backend/src/backend/domain`, not implicitly through an integration test alone. This keeps the suite fast (runs in milliseconds, no Docker needed) and the integration tests lean (they only verify the wiring, not the logic itself).

## 1. Unit tests — `backend/src/backend/domain`

- **Tool**: pytest.
- **Expected coverage**: high (target ≥ 90% of lines) — it's pure logic, no excuse not to test it.
- **What to cover**: every case listed in [business-rules.md](business-rules.md), especially the edge cases already flagged in the document (position hitting zero, sell larger than the position, every asset already above target, negative EPS/book value, app closed for weeks, etc).
- **Already implemented** (Sprint 0): `average_price_calculator`, `corporate_action_applier`, `rebalance_calculator`, `indicator_calculator`, `snapshot_catchup` — see `backend/tests/domain/test_*.py` (40 tests, all passing).
- **Convention**: a `test_*.py` file per module, mirrored under `backend/tests/domain/`. Test names describe the behavior in plain English, not the implementation (`test_does_not_change_the_average_price_on_a_sell`, not `test_apply_sell_function`).
- **Never mock inside the domain layer** — if a domain test "needs" a mock, that's a sign the piece belongs in infrastructure, not domain.

## 2. Integration tests — `backend`

- **Tool**: pytest + FastAPI's `TestClient` (or `httpx.AsyncClient` for async routes) against a real Postgres running in a container (the same `docker-compose.yml`, a separate test database — `investor_test`).
- **What to cover**:
  - Transaction CRUD and the recalculation engine running end to end against the database (not just the domain's pure function — here what matters is that the background task actually runs and persists).
  - B3 statement import: upload → parse → dedup → save, with sample files under `backend/tests/fixtures/`.
  - Startup snapshot catch-up: simulate a past `last_snapshot_date`, start the module, confirm the missing snapshots were created.
  - Authentication and authorization (protected routes rejecting a request without a token).
  - Payload validation (Pydantic) returning 400s in the shape expected by `openapi.yaml`.
- **Isolation**: each test file runs inside a database transaction rolled back at the end (or a `TRUNCATE` between tests) — tests must not depend on execution order or leave state behind for the next one.
- **No external network**: the quote provider is replaced by the mock from section 3 — integration tests must not depend on brapi.dev being up.

## 3. Contract / adapter tests

- **What it is**: tests for the `brapi_provider.py` (and `bcb_provider.py`) adapters against **recorded** responses (real JSON fixtures, captured once and checked into the repo), not against the live API.
- **Why**: proves the adapter correctly parses the provider's real response shape, without making the suite depend on the network or get rate-limited.
- **What to cover**: field mapping (including a missing `logourl` → the fallback handled in another layer), the provider's rate-limit/timeout errors being surfaced as a known domain error (not a generic exception), a historical price series with missing days (holiday/weekend).
- **Updating fixtures**: when the provider changes its response shape, recapture manually and check the new fixture in — don't automate the capture as part of CI.

## 4. E2E tests — desktop app

- **Tool**: Playwright, pointed at the Tauri build's webview (Tauri exposes it via WebDriver for `tauri dev`; alternatively, the same Vite/React frontend can be run directly in a browser for faster tests, since the UI logic doesn't depend on the native shell — only OS-specific features, like the file picker dialog, require the actual Tauri binary).
- **Golden paths covered** (one test per flow, not per screen):
  1. Login → dashboard loads with real data.
  2. Enter a transaction (buy) → position and total value update on screen.
  3. Enter a backdated transaction → confirm the dashboard reflects the recalculation (tolerating the "recalculating..." state before the final result).
  4. Import a B3 statement → import summary shown, positions updated.
  5. Define an allocation target → simulate a contribution → see a suggestion consistent with the target.
  6. Reinvest the dividend balance → balance resets to zero, suggested purchases appear.
  7. Open an indicator's tooltip → explanatory text visible.
- **Out of scope for E2E**: business-rule variations (already exhaustively covered by the domain's unit tests) — E2E only proves the right screen shows the right data.

## 5. Test data

- Simple factories in `backend/tests/factories.py` (reused by integration tests) to build `Transaction`, `Asset`, `Dividend`, etc. with sensible defaults and targeted overrides — avoids tests cluttered with hand-built giant objects.
- B3 statement fixtures (`backend/tests/fixtures/*.csv`), anonymized — never check in one of your own real statements.

## 6. What each sprint delivers in tests

See [sprints.md](sprints.md) — every sprint has its own "Definition of done" with the corresponding tests; there's no separate "test everything at the end" phase. The suite grows together with the feature.

## 7. Running the suite

```bash
# unit (fast, no Docker needed)
cd backend && uv run pytest tests/domain

# integration (needs docker-compose up with the test database)
cd backend && uv run pytest tests/integration

# everything in the backend
cd backend && uv run pytest

# E2E (needs the API running and the desktop app built/in dev mode)
cd frontend && npm run test:e2e
```

## 8. What we deliberately don't test

- The exact behavior of third-party libraries (FastAPI, SQLAlchemy, Tauri) — we trust their contract.
- The accuracy of the external provider's quotes — we validate that we *use* the returned data correctly, not that the data itself is correct (that's the provider's responsibility).
- Load/performance — out of scope for single-user usage.
