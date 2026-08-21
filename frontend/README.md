# Frontend — Minha Carteira (desktop app)

Tauri 2 (native shell) + React + Vite + Tailwind + Recharts. UI layer only — every
business rule lives in the Python backend (see [docs/architecture.md](../docs/architecture.md)).

## Setup

```bash
npm install
```

The app reads `VITE_API_BASE_URL` (defaults to `http://localhost:8000/api`), set in
the repo-root `.env`.

## Running

```bash
npm run dev          # browser only, at http://localhost:1420 (fastest loop)
npm run tauri dev    # native desktop window (needs Rust — see below)
```

The backend must be running (`cd ../backend && uv run uvicorn backend.api.app:app --reload`).

## API client

`src/api/types.ts` is generated from the OpenAPI contract — never edit it by hand.
Regenerate after any change to `docs/openapi/openapi.yaml`:

```bash
npm run generate:api
```

## Tests

```bash
npm run test:e2e     # Playwright, needs the backend up (E2E_PASSWORD, default dev-senha-123)
npm run build        # type-check + production build
```

E2E runs against the Vite build in a real browser rather than the native shell —
the UI logic doesn't depend on Tauri (docs/testing-strategy.md §4).

## Native build (Tauri)

Building the desktop binary needs [Rust + Cargo](https://www.rust-lang.org/tools/install),
which is a separate install from Node. The shell's capabilities are deliberately
minimal (`src-tauri/capabilities/default.json`): file dialogs for the B3 statement
import and data export, plus a CSP that only allows the local API — no arbitrary
network or filesystem access (docs/architecture.md §5).

`src-tauri/icons/` needs an `icon.png` before the first bundle; generate the full
set with `npm run tauri icon path/to/logo.png`.
