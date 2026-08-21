# Architecture — Investment tracking app

Personal, single-user use, local-first, with optional remote access via a personal VPN (Tailscale). Product reference: Investidor10. Backend in Python (uv + FastAPI); desktop frontend in Tauri (Rust shell) + React.

## 1. Context

```
                         ┌────────────────────┐
                         │        You            │
                         └──────────┬───────────┘
                                    │
                          ┌─────────▼──────────┐
                          │    Desktop App        │
                          │  (Tauri + React)      │
                          └─────────┬────────────┘
                                    │  HTTPS/WSS (localhost, or Tailscale
                                    │  for remote access)
                          ┌─────────▼──────────┐
                          │     API Backend      │
                          │  (FastAPI + Python)  │
                          └─────────┬────────────┘
                                    │
        ┌───────────────┬──────────┼──────────────┬────────────────┐
        │                │                          │                  │
┌───────▼──────┐ ┌───────▼───────┐        ┌─────────▼────────┐ ┌───────▼────────┐
│  PostgreSQL   │ │     Redis      │        │  brapi.dev API    │ │   BCB API       │
│ (your data)   │ │ (quote cache)  │        │ (quotes, logos,   │ │ (CDI/Selic,     │
│                │ │                │        │  history)          │ │  free/official) │
└───────────────┘ └────────────────┘        └───────────────────┘ └─────────────────┘

        Additional source (outside the system): B3 statement of transactions,
        downloaded manually by the user and imported as a file upload.
```

There is no automated integration with B3 login (see section 5 — a deliberate security decision). The statement is downloaded by you from the B3 website and imported as a file.

## 2. Containers

| Container | Responsibility | Technology |
|---|---|---|
| Desktop App | Dashboard, portfolio, dividends, targets, contribution simulator — installable native app (macOS/Windows/Linux), UI layer only | Tauri 2 (Rust shell) + React + Vite + Tailwind + Recharts |
| API Backend | Business rules, authentication, orchestration, scheduled jobs | Python + FastAPI, managed with uv |
| PostgreSQL | Source of truth for the user's data | Postgres 16, running in local Docker |
| Redis | Quote cache (avoids hitting free-tier rate limits on external providers) | Redis 7 |

All containers come up via **Docker Compose** on a single machine (your computer, a NAS, or a Raspberry Pi). No dependency on public cloud.

**Deliberately no separate worker container**: at single-user scale, a second process just adds operational overhead for no real benefit. Scheduled jobs (daily snapshot, quote polling) and background recalculation run **inside the same FastAPI process** via APScheduler and async background tasks. If usage ever outgrows this, splitting out a worker is a contained change — the domain layer doesn't know or care who calls it.

## 3. Backend internal architecture (hexagonal)

```
backend/src/backend/
  config.py              # settings from .env (pydantic-settings)
  cli.py                 # hash-password, inspect-statement

  domain/                # pure business rules, no I/O — tested in isolation
    entities.py          # Asset, Transaction, Position, Dividend, CorporateAction,
                          # AllocationTarget, PortfolioSnapshot, Indicator
    average_price_calculator.py
    position_history.py        # replays transactions + corporate actions chronologically
    corporate_action_applier.py
    snapshot_calculator.py     # one day's PortfolioSnapshot from raw history (§8)
    snapshot_catchup.py        # which days were missed while the app was off
    statement_dedup.py         # import deduplication rule (business-rules §7)
    dividend_withholding.py    # withholding at the source per dividend type (§6)
    asset_classification.py    # category inferred from statement evidence (business-rules §7, rule 5)
    rebalance_calculator.py
    indicator_calculator.py    # markers, ceiling price (Bazin), fair price (Graham)

  application/            # use cases — orchestrate domain + ports
    recalculation.py        # retroactive recalculation engine (background task)
    import_b3_statement.py
    enrich_assets.py        # logo/name from the provider, after an import
    snapshot_service.py     # computes + persists a day's snapshot, resolving prices
    startup_catchup.py      # backfills snapshots missed while the app was off
    simulate_contribution.py   # planned — Sprint 5
    reinvest_dividends.py      # planned — Sprint 5

  ports/                  # interfaces that infrastructure implements
    market_data_provider.py   # + MarketDataUnavailableError, the known failure mode
    transaction_repository.py
    price_history_repository.py

  infrastructure/
    persistence/
      database.py           # engine/session factory
      models.py             # SQLAlchemy tables
      repositories.py       # port implementations + domain mapping
    market_data/
      brapi_provider.py     # implements the port, on top of the official `brapi` SDK
      quote_cache.py        # Redis cache decorator (in-memory fallback)
      null_provider.py      # stand-in when no token is configured
      factory.py            # composition root; swappable in tests
      bcb_provider.py       # planned — CDI/Selic, may be unnecessary (see below)
    b3_import/
      statement_parser.py   # CSV/Excel — transactions + corporate actions + dividends
    jobs/
      scheduler.py          # APScheduler wiring, started in the FastAPI lifespan
      daily_snapshot.py
      price_poll.py         # quote polling during market hours, broadcast via WS

  api/
    app.py                 # FastAPI app, lifespan (catch-up + scheduler), CORS
    dependencies.py        # session + auth dependencies
    security.py            # argon2 hashing, JWT issue/verify
    schemas.py             # request/response models, camelCase on the wire
    errors.py              # ApiError -> the `Error` shape in openapi.yaml
    routes/                # routers, mirroring openapi.yaml
    websocket.py           # near-real-time quote channel
```

The quote provider is the official `brapi` SDK wrapped by our own adapter. The SDK is an
implementation detail of `brapi_provider.py`: its typed models and its exception taxonomy
stop at that file, and everything above sees only the port's `Quote`/`HistoricalPrice` and
the single `MarketDataUnavailableError`. It also exposes inflation and prime-rate
endpoints, which may make the planned `bcb_provider` unnecessary — to be decided in
Sprint 6, when CDI/Selic first matter.

Dependency rule: `domain` doesn't know about `infrastructure`. That's what allows swapping the quote provider (e.g. moving from the free tier to a paid one later) without touching any business rule, and testing `domain`/`application` entirely with fakes for the ports — no database, no network.

## 4. Main flows

### 4.1 "Real-time" quotes
1. The `price_poll` job runs every 30s during market hours (B3: 10am–5pm, Brasília time, weekdays), fetching quotes for the assets you hold through `market_data_provider`. Outside those hours it returns immediately — the price doesn't change.
2. Quotes are cached for 30s in Redis, so several readers close together cost one request against the provider's free tier. If Redis is unreachable the cache degrades to an in-process dict; at single-user scale, losing cross-process sharing costs nothing.
3. The backend pushes the update to connected clients over the WebSocket channel.
4. **Degradation is the rule, not the exception.** Any provider failure — rate limit, timeout, HTTP error, unparseable payload — surfaces as a single `MarketDataUnavailableError`, and every consumer has a defined fallback: the dashboard shows cost basis, `price_poll` logs and retries next cycle, snapshots fall back to the local price cache and then to cost. With no `BRAPI_API_TOKEN` configured the composition root substitutes a null provider and `price_poll` is not scheduled at all, so a missing token behaves like any other outage instead of a crash.

### 4.2 Backdated entry + recalculation
1. The route writes the transaction to the ledger, after replaying the prospective history to reject a sell that would exceed the position on its date (business-rules §10).
2. It schedules the recalculation engine as a background task (does not block the API response).
3. The engine replays the asset's **entire** history in chronological order — transactions interleaved with corporate actions — and rewrites the position. Never incremental: that is what makes a backdated entry, edit or delete correct without special cases.
4. While it runs, the API reports `recalculating: true` for the UI to show feedback.
5. Execution is idempotent: running the same recalculation twice produces the same final state — verified by an automated test against the real database.

**Not yet wired**: steps 2 and 3 of business-rules §2 — recalculating the daily snapshots in the affected range, and re-evaluating dividend eligibility. Snapshots are currently rebuilt by the daily job and the startup catch-up (§4.4), so a backdated entry only reaches them on the next run. Closing that gap is tracked with the dividend work in Sprint 6.

### 4.3 B3 statement import
1. Upload of the CSV/Excel file exported from the B3 investor portal.
2. The parser locates the header (exports carry title rows, several sheets, and any of four delimiters — see business-rules §7) and classifies each line: buy/sell, dividend, or corporate action.
3. Deduplication: compares ticker + date + quantity + price against what already exists before saving, so it doesn't duplicate what you already entered manually.
4. Unknown tickers are registered from the statement itself, with the category inferred from evidence in the file (business-rules §7, rule 5). The typo guard in §10 applies to hand-typed entries only.
5. Newly saved records trigger the same recalculation engine from 4.2.
6. Afterwards, in the background, `enrich_assets` fills in logo and display name from the quote provider — never blocking, never failing the import.

**Nothing aborts the batch.** A row the parser cannot decide (unrecognized movement, no readable ticker, underivable corporate-action factor) goes to a review queue with its reason. A sell that exceeds the position is flagged rather than rejected, and its ticker is left out of recalculation until corrected — §10 again, where a batch cannot be judged row by row.

### 4.4 Catch-up on startup

Since the backend doesn't run 24/7 (the computer gets turned off, the app gets closed), `daily_snapshot` can miss days. A `SystemState` key-value table stores `last_snapshot_date` and `last_run_at`. On API startup:
1. Compares `last_snapshot_date` to today's date.
2. `compute_missing_snapshot_dates` (backend/src/backend/domain) computes the missing days.
3. The same recalculation engine from section 4.2 processes each missing day, in order, updating `last_snapshot_date` incrementally — if interrupted midway, the next startup resumes from the right point.

Full detail in [business-rules.md §8.1](business-rules.md#81-catch-up-on-startup).

### 4.5 Scheduled jobs
- `daily_snapshot`: runs after market close, records the day's `PortfolioSnapshot` (total, by category, contribution/appreciation/reinvested-dividend breakdown).
- `price_poll`: described in 4.1.
- Failure alerts: since there's no on-call team, a failed job writes a structured log and also raises a simple notification (e.g. email or push) so you know a recalculation didn't complete — important for trusting the numbers.

## 5. Security

- Single-user authentication: username + password (argon2), session via short-lived JWT + refresh token.
- No B3 login integration (a deliberate decision — never store third-party credentials).
- Secrets (API keys) in environment variables, never in the repository.
- HTTPS even locally, via Tailscale's own certificate (which already provides end-to-end TLS) or mkcert for LAN-only use.
- Rate limiting on API routes; payload validation on every route (Pydantic models, shared with the OpenAPI schemas).
- CORS restricted to the desktop app's own origins (the Vite dev server and the Tauri webview) — the API is never open to arbitrary web origins.
- Automatic daily Postgres backup (`pg_dump`) + free data export on demand (CSV/JSON) by the user.
- **Tauri**: the desktop app explicitly declares, in `tauri.conf.json`, which capabilities it has access to (network only to the configured API host, filesystem only for the CSV import / backup export dialogs). Unlike Electron, there's no Node.js exposed to the frontend — the desktop process's attack surface is much smaller.

## 6. Observability

Current state: the standard library's `logging`, configured by uvicorn. Messages at the
boundaries are deliberately specific about *which* failure occurred, because a personal
app has no on-call to interpret them — a rejected WebSocket handshake says whether the
token was expired, foreign-signed or of the wrong type; a missing provider token says so
once at startup; a failed `daily_snapshot` says the day's value was not recorded.

Planned (Sprint 7–8, none of it built yet):

- Structured logs (structlog), replacing the plain formatter.
- Correlation via `request_id` between API requests and the background tasks they trigger.
- A "last job run" panel in the app under Settings, reading `last_snapshot_date` and `last_run_at` from the `system_state` table — minimal visibility without needing Grafana/Datadog.
- Failure alerts for jobs, so a recalculation that never completed does not pass unnoticed.

## 7. Deployment

- `docker-compose.yml` at the repo root brings up `api`, `postgres`, `redis`. Configured to start with the system (OS service/daemon), since the desktop app depends on it being up.
- The desktop app points to the local URL (`localhost`) by default, or to the Tailscale hostname if you want to open the app on another machine pointing at the same backend — configurable in the app's Settings.
- No public port exposed to the internet.

## 8. Repository structure

```
/
  backend/
    pyproject.toml       # uv-managed
    alembic.ini
    migrations/          # Alembic revisions
    src/backend/
      domain/ application/ ports/ infrastructure/ api/
    tests/
      domain/            # pure unit tests
      b3_import/         # statement parser
      market_data/       # provider contract tests (recorded fixtures)
      api/               # small unit tests of API helpers
      integration/       # against a real Postgres
      fixtures/          # anonymized statements + recorded provider responses
  frontend/
    package.json
    playwright.config.ts
    src/                 # React + Vite (api/, components/, hooks/, pages/, lib/)
    src-tauri/           # native Rust shell (capabilities config, per-OS build)
    e2e/                 # Playwright specs
  docs/
    architecture.md
    business-rules.md
    sprints.md
    testing-strategy.md
    openapi/
      openapi.yaml
  data/                  # Postgres + Redis files, bind-mounted (gitignored)
  docker-compose.yml
  .env                   # secrets, gitignored (.env.example is the template)
```

Backend and frontend are independent projects with their own package managers (`uv` for Python, `npm` for the frontend) — they only communicate over HTTP/WebSocket, so there's no reason to force them into a single-language monorepo.
