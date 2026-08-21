# Sprint plan

Suggested sequence respecting technical dependencies (e.g. you can't have a contribution simulator without a computed position; you can't have quotes without a data provider integrated). Sprints of ~1-2 weeks, solo pace. "Done" in every sprint always includes the corresponding tests — it's not a separate phase (see [testing-strategy.md](testing-strategy.md) for the full strategy).

## Sprint 0 — Foundation ✅ (done)

- Documentation: [architecture.md](architecture.md), [business-rules.md](business-rules.md), [openapi/openapi.yaml](openapi/openapi.yaml)
- `backend/`: uv-managed Python project, FastAPI + pytest
- `backend/src/backend/domain`: pure business rules already implemented and tested — average price, recalculation engine (calculation), corporate actions, rebalancing/contribution, indicators (Bazin/Graham/markers), startup snapshot catch-up (40 passing tests)
- `docker-compose.yml` (Postgres + Redis)

## Sprint 1 — Backend core: transactions and position ✅ (done)

- `backend`: SQLAlchemy models mirroring the domain entities (`assets`, `transactions`, `positions`), Alembic migrations (initial migration also seeds a starter B3 asset catalog)
- Single-user authentication (argon2 password + JWT access/refresh, see business-rules and architecture §5); `uv run python -m backend.cli hash-password` generates `APP_PASSWORD_HASH`
- Endpoints: `POST/GET/PATCH/DELETE /transactions`, `GET /positions`, `GET /assets` (autocomplete) + `GET /assets/{ticker}`
- Recalculation engine wired to real Postgres — triggers on transaction create/edit/delete, runs as a background task, exposes `recalculating` in responses
- Sanity checks (sell larger than position on any date — including via edit/delete — returns 422 `SELL_EXCEEDS_POSITION`; unknown ticker returns 400 `UNKNOWN_TICKER`)

**Definition of done**: ✅ integration tests for the endpoints against a real Postgres (`backend/tests/integration/`, 26 tests); idempotency test for the recalculation engine running against the database; backdated-transaction test + manual smoke test confirming the position recalculates correctly.

## Sprint 2 — B3 statement import ✅ (done)

- CSV/Excel parser for the B3 movement statement (`infrastructure/b3_import/statement_parser.py`) → transactions, dividends (gross/net via `domain/dividend_withholding.py`), corporate actions (factor derived from the position held on the event date)
- Deduplication against existing transactions (`domain/statement_dedup.py`: ticker + date + quantity + price within a cent; ambiguous → review)
- "Rows needing manual review" queue persisted in `import_review_rows` and returned in the response (unknown movement types, unknown tickers, underivable factors, post-import inconsistencies)
- `POST /import/b3-statement` endpoint + read-only `GET /corporate-actions`
- Recalculation engine (and the sell sanity check) now replays corporate actions interleaved with transactions (`domain/position_history.py`); batch imports flag a sell-exceeds-position for review instead of rejecting (business-rules §10)

**Definition of done**: ✅ parser unit tests with anonymized sample files (`backend/tests/fixtures/`) covering buy, sell, dividend/JCP/REIT income, split, bonus shares, reverse split, CSV and Excel; deduplication tests (re-importing the same file creates nothing new; a manual entry blocks its imported twin). 93 tests passing.

## Sprint 3 — Quotes, snapshots, and catch-up ✅ (done)

- brapi.dev adapter (`infrastructure/market_data/brapi_provider.py`) implementing the `market_data_provider` port; contract tests against recorded JSON fixtures
- `price_poll` job (APScheduler, market hours only) broadcasting over the `/ws/quotes` WebSocket channel (token-authenticated)
- `daily_snapshot` job + `domain/snapshot_calculator.py` (total/per-category value, cumulative contributions, cumulative reinvested dividends — growth breakdown by residual served by `GET /portfolio/growth-breakdown`)
- `system_state` table persisting `last_snapshot_date` / `last_run_at`; `portfolio_snapshots` and `price_history` (local closing-price cache — a multi-day backfill costs one provider request per ticker)
- Startup catch-up wired into the FastAPI lifespan (background thread, resumable day by day); `ENABLE_JOBS=false` turns scheduler/catch-up off in tests
- Redis quote cache with graceful in-memory fallback when Redis is unreachable
- Dashboard endpoints: `GET /portfolio/summary`, `GET /portfolio/snapshots`; `GET /positions` now enriched with live quotes (provider outage degrades to cost basis, never fails)

**Definition of done**: ✅ integration test "the app was off for 5 days" backfills exactly 5 snapshots, resumable/idempotent; provider mocked in every test (no network); WebSocket tests delivering a price update to a connected client and rejecting bad tokens. 115 tests passing.

## Sprint 4 — Desktop app (Tauri) — foundation ✅ (done)

- Tauri 2 + React + Vite + Tailwind 4 project scaffold (`frontend/`), with `src-tauri` capabilities scoped to file dialogs only and a CSP restricted to the local API
- Login screen (JWT pair stored locally, transparent refresh on 401, protected routes)
- Dashboard: summary cards, growth chart (Recharts), allocation-by-category donut, positions table with initials avatar colored by category
- TS types generated from `openapi.yaml` (`npm run generate:api`), consumed by the UI
- Live quotes over the `/ws/quotes` WebSocket refine the table without a refetch, with reconnect backoff
- CORS added to the backend for the Vite dev server and Tauri origins (found by the E2E test — a browser/webview client cannot call the API without it)

**Definition of done**: ✅ the app opens and shows real data from the local API (verified against a live backend + Postgres); 4 Playwright E2E tests covering the login flow, wrong password, route protection and logout.

> **Note**: building the native `.app` needs Rust + Cargo installed, which is not yet
> set up in this environment — the web build, the dev flow and the E2E suite all run
> without it. Installing Rust is the only remaining step to produce the desktop binary
> (packaging itself is Sprint 8).

## Sprint 5 — Allocation targets, contributions, and reinvestment

- Screen for defining targets (category % + weight per asset, equal split as the default)
- Contribution simulator (`POST /allocation-targets/simulate`) with the suggested-purchases screen
- "Reinvest dividends" flow using the accumulated dividend balance as the contribution amount
- **Positions grouped into collapsible sections by category** (see below)

### Positions grouped by category

The flat positions table becomes one collapsible section per category — the same
shape the allocation targets use, so the portfolio reads against the target it is
being measured by.

```
▾ Ações                    R$ 12.450,00   64,1%
    ITSA4    100    R$ 9,10   +12,3%
    ALOS3     50   R$ 20,00    -2,1%

▸ FIIs                      R$ 6.980,00   35,9%
▸ Renda Fixa                       R$ 0,00    0,0%
```

- Section header carries the category name, its total value and its share of the
  portfolio — the numbers that matter when comparing against an allocation target.
- Sections are ordered by portfolio weight, heaviest first.
- Expand/collapse state persists across reloads (localStorage), so the categories
  someone actually watches stay open.
- A category with no positions is hidden **unless** an allocation target exists for
  it — a 0% row is noise on its own, but it is the whole point once you have set a
  target you are not yet filling.
- The header is a real `button` with `aria-expanded`; grouping must not cost
  keyboard or screen-reader access to the table.

**Definition of done**: E2E test for the full "define target → simulate contribution → review suggestion" flow; integration tests validating that category percentages are checked in `PUT /allocation-targets`; E2E test collapsing a category and confirming its assets are hidden while the header totals stay visible; component test covering the grouping totals, the weight ordering, and the empty-category rule in both directions.

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
