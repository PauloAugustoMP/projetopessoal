# Sprint plan

Suggested sequence respecting technical dependencies (e.g. you can't have a contribution simulator without a computed position; you can't have quotes without a data provider integrated). Sprints of ~1-2 weeks, solo pace. "Done" in every sprint always includes the corresponding tests — it's not a separate phase (see [testing-strategy.md](testing-strategy.md) for the full strategy).

## Sprint 0 — Foundation ✅ (done)

- Documentation: [architecture.md](architecture.md), [business-rules.md](business-rules.md), [openapi/openapi.yaml](openapi/openapi.yaml)
- `backend/`: uv-managed Python project, FastAPI + pytest
- `backend/src/backend/domain`: pure business rules already implemented and tested — average price, recalculation engine (calculation), corporate actions, rebalancing/contribution, indicators (Bazin/Graham/markers), startup snapshot catch-up (40 passing tests)
- `docker-compose.yml` (Postgres + Redis)

## Sprint 1 — Backend core: transactions and position

- `backend`: SQLAlchemy models mirroring the domain entities, Alembic migrations
- Single-user authentication (password + JWT, see business-rules and architecture §5)
- Endpoints: `POST/GET/PATCH/DELETE /transactions`, `GET /positions`, `GET /assets` (autocomplete)
- Recalculation engine wired to real Postgres — triggers on transaction create/edit/delete, runs as a background task
- Sanity checks (sell larger than position, unknown ticker)

**Definition of done**: integration tests for the endpoints against a real Postgres; idempotency test for the recalculation engine running against the database; manually enter a backdated transaction and confirm the position recalculates correctly.

## Sprint 2 — B3 statement import

- CSV/Excel parser for the B3 statement → transactions, dividends (gross/net), corporate actions
- Deduplication against existing transactions
- "Rows needing manual review" queue when a match is ambiguous
- `POST /import/b3-statement` endpoint

**Definition of done**: unit tests for the parser using sample (anonymized) real files covering buy, sell, dividend, split, bonus shares, reverse split; deduplication test (importing the same line twice doesn't duplicate it).

## Sprint 3 — Quotes, snapshots, and catch-up

- Quote provider adapter (brapi.dev) implementing the `market_data_provider` port
- `price_poll` job (near real-time) + WebSocket channel
- `daily_snapshot` job (total portfolio value, by category, contribution/appreciation/dividend breakdown)
- Persisted `last_snapshot_date` / `last_run_at` state
- Startup catch-up: on API boot, compares `last_snapshot_date` to today and recalculates the days that were missed (`compute_missing_snapshot_dates`, already implemented in the domain layer)
- Redis as a quote cache (avoids exhausting the free tier's rate limit)

**Definition of done**: integration test simulating "the app was off for 5 days" and verifying the 5 snapshots get backfilled on startup; quote provider mocked so tests don't depend on the network; WebSocket test delivering a price update to a connected client.

## Sprint 4 — Desktop app (Tauri) — foundation

- Tauri + React + Vite project scaffold (`frontend/`)
- Login screen
- Dashboard: total portfolio value, summary cards, growth chart, allocation by category, positions table (with logo/avatar by category)
- TS client generated from `openapi.yaml`, consumed by the UI

**Definition of done**: the app opens and shows real data from the local API; manual smoke test on the target OS (at least macOS, the user's environment); E2E test for the login flow.

## Sprint 5 — Allocation targets, contributions, and reinvestment

- Screen for defining targets (category % + weight per asset, equal split as the default)
- Contribution simulator (`POST /allocation-targets/simulate`) with the suggested-purchases screen
- "Reinvest dividends" flow using the accumulated dividend balance as the contribution amount

**Definition of done**: E2E test for the full "define target → simulate contribution → review suggestion" flow; integration tests validating that category percentages are checked in `PUT /allocation-targets`.

## Sprint 6 — Indicators and dividends

- `GET /assets/{ticker}/indicators`: P/E, P/B, DY, ROE with a colored marker + tooltip
- Ceiling price (Bazin) and fair price (Graham) on the asset detail screen
- Dividend calendar (ex-date / payment date) + upcoming dividends list
- Manual entry for an announced dividend

**Definition of done**: E2E test opening an indicator's tooltip and checking the text; integration test for the calendar returning events within the correct date range.

## Sprint 7 — Security, backup, and export

- Automatic daily Postgres backup (scheduled `pg_dump`)
- Free data export (CSV/JSON) on demand
- Audit log for backdated changes + "undo last change"
- Review of rate limiting, payload validation on every route, Tauri capabilities scoped to the minimum needed

**Definition of done**: automated test restoring a backup and checking data integrity; test for the undo flow.

## Sprint 8 — Packaging and final hardening

- Tauri installer build (macOS — the user's environment; Windows/Linux later if needed)
- Backend configured to start with the system (service/daemon)
- Full pass of E2E tests covering the complete golden paths
- Review of the "last job run" panel (Settings) and failure alerts

**Definition of done**: install the `.app` from scratch on a clean machine and complete the "open app → enter transaction → import statement → view dashboard → simulate contribution" flow without touching any code.
