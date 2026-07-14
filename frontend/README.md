# DAFI Sentinel Dashboard (PR5)

The React + TypeScript + Vite dashboard. Talks to the FastAPI workbench
server through the dev-server proxy in `vite.config.ts`.

## Quick start

```bash
# 1. Install JS deps (one-time)
npm install

# 2. Start the FastAPI server in another shell
uv run uvicorn dafi_sentinel.api.app:default_workbench_app --reload

# 3. Start the dashboard
npm run dev
```

The dashboard proxies `/sessions`, `/evidence`, `/qa`, `/charts`,
`/roles`, and `/audits` to `http://127.0.0.1:8000`.

## Build and test

```bash
npm run build   # tsc --noEmit && vite build
npm run test    # vitest run
```

## What lives here

* `src/api/` — fetch client and TanStack Query hooks.
* `src/auth/` — `AuthGate` (redirects to `/login` when no session),
  `useAuth` (session bootstrap + logout).
* `src/pages/` — Login, Evidence list/detail, Q&A, Charts, Roles, Audits.
* `src/test/` — Vitest setup + tests for the auth gate and each page.
