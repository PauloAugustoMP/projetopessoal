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
  domain/                # pure business rules, no I/O — tested in isolation
    entities.py          # Asset, Transaction, Position, Dividend, CorporateAction,
                          # AllocationTarget, PortfolioSnapshot, Indicator
    average_price_calculator.py
    corporate_action_applier.py
    rebalance_calculator.py
    indicator_calculator.py    # markers, ceiling price (Bazin), fair price (Graham)
    snapshot_catchup.py

  application/            # use cases — orchestrate domain + ports
    record_transaction.py
    import_b3_statement.py
    simulate_contribution.py
    reinvest_dividends.py
    get_portfolio_growth.py

  ports/                  # interfaces that infrastructure implements
    market_data_provider.py
    transaction_repository.py
    price_history_repository.py

  infrastructure/
    persistence/          # SQLAlchemy repository implementations
    market_data/
      brapi_provider.py         # implements market_data_provider port
      bcb_provider.py           # CDI/Selic
    b3_import/
      statement_csv_parser.py   # extracts transactions + corporate actions + dividends
    jobs/
      daily_snapshot.py
      price_poll.py             # quote polling during market hours, broadcast via WS

  api/
    app.py                 # FastAPI app instance
    routes/                 # routers, mirroring openapi.yaml
    websocket.py             # near-real-time quote channel
```

Dependency rule: `domain` doesn't know about `infrastructure`. That's what allows swapping the quote provider (e.g. moving from the free tier to a paid one later) without touching any business rule, and testing `domain`/`application` entirely with fakes for the ports — no database, no network.

## 4. Main flows

### 4.1 "Real-time" quotes
1. The `price_poll` job runs every 15–30s during market hours (B3: 10am–5pm, Brasília time), fetching quotes for the assets you hold through `market_data_provider`.
2. The price is cached in Redis (avoids re-querying the external API if multiple clients are connected).
3. The backend pushes the update to the connected desktop app over WebSocket.
4. Outside market hours, the job runs at a much longer interval (or not at all), since the price doesn't change.

### 4.2 Backdated entry + recalculation
1. `record_transaction` writes the transaction to the immutable ledger.
2. It schedules the `recalculation engine` as a background task (does not block the API response).
3. The engine recalculates, in chronological order: the asset's position/average price → the daily portfolio snapshots in the affected range (fetching historical prices via `market_data_provider` if not already cached) → dividend eligibility in that range.
4. While it runs, the API exposes a status (`recalculating: true`) for the UI to show feedback.
5. Execution is idempotent: running the same recalculation twice produces the same final state — a property verified by an automated test.

### 4.3 B3 statement import
1. Upload of the CSV/Excel file exported from the B3 investor portal.
2. The parser classifies each line: buy/sell, dividend (gross/net), or corporate action (split/reverse split/bonus shares/subscription rights).
3. Deduplication: compares ticker + date + quantity + price against what already exists before saving, so it doesn't duplicate what you already entered manually.
4. Newly saved records trigger the same recalculation engine from 4.2.

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
- Automatic daily Postgres backup (`pg_dump`) + free data export on demand (CSV/JSON) by the user.
- **Tauri**: the desktop app explicitly declares, in `tauri.conf.json`, which capabilities it has access to (network only to the configured API host, filesystem only for the CSV import / backup export dialogs). Unlike Electron, there's no Node.js exposed to the frontend — the desktop process's attack surface is much smaller.

## 6. Observability

- Structured logs (structlog) in the backend.
- Correlation via `request_id` between API requests and the background tasks they trigger.
- A simple "last job run" panel (daily_snapshot, price_poll) in the app itself, under Settings — minimal visibility without needing Grafana/Datadog for a personal project.

## 7. Deployment

- `docker-compose.yml` at the repo root brings up `api`, `postgres`, `redis`. Configured to start with the system (OS service/daemon), since the desktop app depends on it being up.
- The desktop app points to the local URL (`localhost`) by default, or to the Tailscale hostname if you want to open the app on another machine pointing at the same backend — configurable in the app's Settings.
- No public port exposed to the internet.

## 8. Repository structure

```
/
  backend/
    pyproject.toml     # uv-managed
    src/backend/
      domain/
      application/
      ports/
      infrastructure/
      api/
    tests/
      domain/
  frontend/
    package.json
    src/                # React + Vite
    src-tauri/          # native Rust shell (capabilities config, per-OS build)
  docs/
    architecture.md
    business-rules.md
    sprints.md
    testing-strategy.md
    openapi/
      openapi.yaml
  docker-compose.yml
```

Backend and frontend are independent projects with their own package managers (`uv` for Python, `npm` for the frontend) — they only communicate over HTTP/WebSocket, so there's no reason to force them into a single-language monorepo.
