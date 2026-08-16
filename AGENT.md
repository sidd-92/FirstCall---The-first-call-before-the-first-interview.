# AGENT.md

Instructions for coding agents (Antigravity, Claude Code, or any other agent) working in this repo.

## Setup

Follow **README.md §0 ("Setup & Getting Admin Access")** top to bottom for first-run setup and getting HR-dashboard admin access. Do not improvise a setup sequence — that section exists precisely because the naive order of operations doesn't work here.

## Things agents commonly get wrong in this repo

- **Editing `.env` does not restart running containers.** Docker Compose reads `env_file` once, at container *creation*, not live. After changing any value in `.env`, the affected container must be rebuilt/recreated, not just left running:
  ```
  docker compose up -d --build <service>
  ```
  `docker compose restart <service>` is *not* enough — it restarts the process inside the existing container without re-reading `.env`.

- **`PLATFORM_ADMIN_EMAIL` requires an Auth0 tenant-side Action first.** Auth0 Access Tokens omit the `email` claim by default — only ID Tokens carry it. `services/backend/src/auth.py`'s `require_admin` reads `email` off the Access Token; without a Login Action that explicitly adds it (README §0.2), admin access silently 403s forever, no matter what `PLATFORM_ADMIN_EMAIL` is set to. Set this up *before* the first login.

- **Order matters for admin access:** sign up first with the intended admin account (auto-provisions a `Business` row, not yet admin), *then* set `PLATFORM_ADMIN_EMAIL` to that exact email, rebuild the backend container, then log out and back in to get a fresh token. Setting `PLATFORM_ADMIN_EMAIL` before anyone has signed up with that email does nothing yet — see README §0.3.

- Only **one** admin email is supported at a time (`PLATFORM_ADMIN_EMAIL` is a single exact-match string, not a list) — this is intentional for a hackathon-scale showcase, not a bug to fix.
