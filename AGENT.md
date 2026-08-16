# AGENT.md

Instructions for coding agents (Antigravity, Claude Code, or any other agent) working in this repo.

## Setup

Follow **README.md §0 ("Setup & Getting Admin Access")** top to bottom for first-run setup and getting HR-dashboard admin access. Do not improvise a setup sequence — that section exists precisely because the naive order of operations doesn't work here.

## Things agents commonly get wrong in this repo

- **Editing `.env` does not restart running containers.** Docker Compose reads `env_file` once, at container *creation*, not live. After changing any value in root `.env`, always run:
  ```
  make restart-backend
  ```
  Never use `docker compose restart backend` — it restarts the process inside the existing container without re-reading `.env`, so the old value stays in effect. This has already caused real, repeated confusion in this project (looked exactly like an Auth0/permissions bug both times) — always use the make target, don't hand-roll `docker compose up -d --build backend` either, just to remove any chance of typo-ing it into a plain restart.

- **`PLATFORM_ADMIN_EMAIL` requires an Auth0 tenant-side Action first.** Auth0 Access Tokens omit the `email` claim by default — only ID Tokens carry it. `services/backend/src/auth.py`'s `require_admin` reads `email` off the Access Token; without a Login Action that explicitly adds it (README §0.2), admin access silently 403s forever, no matter what `PLATFORM_ADMIN_EMAIL` is set to. Set this up *before* the first login.

- **Order matters for admin access:** sign up first with the intended admin account (auto-provisions a `Business` row, not yet admin), *then* set `PLATFORM_ADMIN_EMAIL` to that exact email, rebuild the backend container, then log out and back in to get a fresh token. Setting `PLATFORM_ADMIN_EMAIL` before anyone has signed up with that email does nothing yet — see README §0.3.

- **There are TWO admin-email env vars, not one, and they don't share a source of truth.** `PLATFORM_ADMIN_EMAIL` (backend, root `.env`) is what actually gates `/admin/*` API access. `VITE_PLATFORM_ADMIN_EMAIL` (`apps/dashboard/.env.local`) is a completely separate, frontend-only, build-time var that only controls whether the dashboard *shows* the Admin nav link/page (`AppLayout.tsx`). If they drift out of sync, the API still works correctly but the UI silently hides the admin link — no error, no 403, just a confusing "I'm admin but I don't see it." Set both to the same email, and remember `VITE_*` vars need a Vite dev-server restart to take effect (not just a file save).

- Only **one** admin email is supported at a time per var (`PLATFORM_ADMIN_EMAIL` is a single exact-match string, not a list) — this is intentional for a hackathon-scale showcase, not a bug to fix.
