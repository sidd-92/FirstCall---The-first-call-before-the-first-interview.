# FirstCall — Technical Documentation

**Tagline:** The first call, before the first interview.

**Event:** Caspian AI Agent Hackathon
**Stack:** Caspian SDK (Python) · FastAPI · React + Vite + Shadcn + TailwindCSS · SQLite · Auth0 · Turborepo + Docker Compose hybrid monorepo

---

## 0. Setup & Getting Admin Access (Judges Start Here)

This section exists so a fresh clone can be run and reviewed end-to-end, including the HR admin surface, without any prior context.

### 0.1 Prerequisites
- Docker + Docker Compose
- Node.js 22+ and `pnpm`
- An **Auth0 tenant** you control (a free dev tenant is enough — see §7.2.1). You'll need a Regular Web App / SPA registered in it, with its Domain, Client ID, and an API Audience.
- API keys: `CASPIAN_API_KEY`, `DISCORD_BOT_TOKEN`, `ANTHROPIC_API_KEY` (or a Gemini key, if using the Gemini-backed FAQ fallback — see `services/mcp-server/src/agents/gemini_client.py`)

### 0.2 Configure Auth0 to actually carry an email claim

**This step is easy to miss and will silently break admin access if skipped.** Auth0 Access Tokens do **not** include profile claims like `email` by default — only ID Tokens do. `services/backend/src/auth.py`'s `require_admin` and `_require_verified_email` both read `claims.get("email")` off the *Access Token*. If that claim is missing, `require_admin` denies every request, no matter what `PLATFORM_ADMIN_EMAIL` is set to (see `auth.py:175-184` for the exact known-limitation note).

Fix this once, in your Auth0 tenant, before first login:
1. Auth0 Dashboard → **Actions** → **Flows** → **Login**
2. Add a custom Action (or Rule, on older tenants) that adds the email claim to the Access Token, e.g.:
   ```js
   exports.onExecutePostLogin = async (event, api) => {
     if (event.authorization) {
       api.accessToken.setCustomClaim('email', event.user.email);
     }
   };
   ```
   (Namespaced claims like `https://firstcall.app/email` also work — just keep `auth.py` in sync with whatever claim name you use.)
3. Deploy the Action and add it to the Login flow.

### 0.3 First run and getting admin access

1. `cp .env.example .env` (root) and fill in the keys from §0.1, leaving `PLATFORM_ADMIN_EMAIL` **blank** for now.
2. `cp apps/dashboard/.env.example apps/dashboard/.env` and `cp apps/landing/.env.example apps/landing/.env`, filling in the `VITE_AUTH0_*` values from your tenant.
3. `make dev` — starts `mcp-server` + `backend` (Docker) and the dashboard/landing dev servers (Turborepo).
4. Open the dashboard, sign up / log in with **the account you want to be admin** (any real email works — this is the account judges should use).
5. On first login, a `Business` row is auto-provisioned for that Auth0 `sub` (see `auth.py`'s `_get_or_provision_business`) with `status = unrequested` — this is expected; it's not admin yet.
6. Note the exact email you just signed up with, set it as `PLATFORM_ADMIN_EMAIL` in the root `.env`, then restart the backend so it picks up the new value. **Editing `.env` alone does nothing while the container keeps running** — Docker Compose reads `env_file` once, at container creation, not live, so the backend container must actually be recreated, not just left up. Always use:
   ```
   make restart-backend
   ```
   (never `docker compose restart backend`, and don't hand-roll the `docker compose up -d --build backend` command either — this has already been gotten wrong twice by doing a plain restart instead of a rebuild+recreate; use the make target so it's not possible to get it wrong again.)
7. Log out and back in (so the refreshed session re-issues a token) — this account now passes `require_admin` and can access `/admin/*` (approve/reject business access requests, etc.) in the dashboard.
8. Also set `VITE_PLATFORM_ADMIN_EMAIL` in `apps/dashboard/.env.local` to the **same** email, then restart the dashboard's Vite dev server. This is a second, separate env var from the backend's `PLATFORM_ADMIN_EMAIL` — it only controls whether the dashboard *shows* the Admin nav link/page client-side (`AppLayout.tsx`); real enforcement is entirely server-side (`require_admin`), so a mismatch here doesn't block API access, it just hides the UI for an account that would otherwise be let in. Easy to miss since the API works fine and nothing errors — the symptom is just "I'm admin but I don't see the Admin link."

Only one admin email is supported at a time (`PLATFORM_ADMIN_EMAIL` is a single exact-match string, not a list — see `.env.example`'s note) — this is intentional for a hackathon-scale showcase, not a bug. **Both `PLATFORM_ADMIN_EMAIL` (backend) and `VITE_PLATFORM_ADMIN_EMAIL` (dashboard) must be kept in sync manually** — there is no shared source of truth between them, and nothing warns you when they drift.

---

## 1. Overview

FirstCall is an AI-assisted hiring assistant for small businesses that don't have a dedicated recruiter or ATS. It handles the earliest, most repetitive part of hiring — answering candidate FAQs and running a non-technical first-round screening conversation — across two communication channels (Email and Discord) through a single AI agent identity, powered by the [Caspian SDK](https://github.com/TryCaspian/caspian-sdk).

Instead of a human answering the same questions over and over and manually coordinating first-round chats, FirstCall:

1. Publishes job openings on a public landing page
2. Collects structured applications (resume, phone, address, basic info)
3. Answers candidate FAQs automatically over email
4. Runs a fixed, non-technical first-round screening conversation over Discord — explaining the role and asking about experience and salary expectations
5. Gives HR a single dashboard to review every candidate's full journey, optionally get an AI-generated summary/score, and manually decide who moves to the next round

FirstCall satisfies the hackathon's core requirement — **one agent, one handler, at least two supported communication channels** — via its candidate-facing agent, which operates on Email and Discord through a single `on_message` handler.

---

## 2. Problem Statement

Small businesses without a dedicated HR/recruiting function face:

- Repetitive FAQ answering for every job posting (remote/hybrid, salary band, requirements, deadlines)
- No structured first-round screen — informal DMs/calls that are hard to track or compare across candidates
- No single view of "who applied for what, and where are they in the process"
- Existing ATS platforms (Greenhouse, Lever, etc.) are built for companies with dedicated recruiters and are overkill/unaffordable for a 5–50 person business

FirstCall targets this underserved segment: too small for an ATS, too busy to do it all manually.

---

## 3. Product Flow

### 3.1 Candidate-facing flow

```
Landing Page → Application Form → Job-tagged Email → FAQ Handling → HR-Assigned Screening (Discord) → HR Review
```

**Step-by-step:**

1. **Landing page** lists all open job postings. Clicking a posting shows the full job description and requirements.
2. **Application form** on the job detail page collects:
   - Resume (file upload, stored as-is — not parsed by an LLM in the MVP)
   - Phone number
   - Address
   - Basic candidate details (name, etc.)
3. A button on the page **copies a `mailto:` link** pre-filled with the agent's email address and a job-specific tag (e.g. in the subject line, `Application: Frontend Developer [JOB-042]`), so that when the candidate emails, the system can automatically associate the email with the correct job posting.
4. **Candidate emails the job-tagged address.** Agent 1 (candidate-facing) auto-responds with that job's **FAQ section**, pulled from a per-job configuration document. Any further questions the candidate asks are also answered over email, grounded in that same job doc.
   - **Email is FAQ-only.** It never carries the screening conversation.
5. **HR manually assigns the Discord screening round** to a candidate from the dashboard (not automatic — HR decides who's worth screening).
6. **Discord screening.** The agent runs a **fixed, non-technical, phone-interview-style conversation**:
   - Explains the role in plain terms
   - Asks about the candidate's relevant experience
   - Asks about salary expectations
   - All answers are **typed text** — no voice/audio recording (see §7, out of scope).
7. **HR reviews.** In the dashboard, HR can read the full screening transcript alongside the candidate's application details and complete chat/email history. HR may optionally trigger an **on-demand AI review** for a summary/score of the transcript (not automatic per-candidate — kept on-demand to control LLM cost).
8. **HR clicks "Shortlist for Next Round"** to advance the candidate's pipeline stage. This is a distinct, separate action from actually sending an interview invite — shortlisting is an internal decision; scheduling/inviting is a deliberate follow-up action, preventing premature candidate notification.

### 3.2 Pipeline stages

```
Applied → Screening Assigned → Screening Completed → Shortlisted → Interview Scheduled → Confirmed
```

---

## 4. Agent Architecture

FirstCall uses a **two-agent structure**, both built on the Caspian SDK, within a single submission/repository.

### Agent 1 — Candidate-facing (qualifying agent)
- **Channels:** Email + Discord
- **Handler:** one `on_message` handler, satisfying the hackathon's "at least two channels, one handler" requirement
- **Responsibilities:**
  - Auto-respond to job-tagged emails with the relevant FAQ section
  - Answer follow-up candidate questions over email
  - Run the fixed screening question sequence over Discord once HR assigns it
  - Record all Q&A into the encrypted conversation store

### Agent 2 — HR/ops-facing (notification agent)
- **Channels:** flexible (e.g. email or Discord notification to the business owner)
- **Responsibilities:**
  - Notify the business owner/HR when a new candidate applies
  - Notify HR when a screening round is completed and ready for review
  - Does not need to independently satisfy the two-channel rule — Agent 1 already qualifies the submission

---

## 5. MCP Server Layer

Rather than calling the Caspian REST API or SDK directly and scattering that logic across the codebase, FirstCall wraps the `caspian-sdk` Python client inside an **MCP (Model Context Protocol) server**. This exposes messaging capability as a set of well-defined tools, usable by any MCP-capable agent — not just the two built here.

**Why an MCP server, not raw SDK calls inline:**
- Centralizes all Caspian interaction in one place, alongside the encrypted storage and access-control layer
- The SDK's own roadmap lists an MCP server as a planned-but-unshipped feature — building one here is a genuine, original contribution on top of the SDK, not a duplicate of existing functionality
- Keeps agent logic, storage logic, and channel logic cleanly separated

**MCP tools exposed:**

| Tool | Purpose |
|---|---|
| `list_channels` | Lists channels currently connectable on this deployment |
| `connect_channel` | Connects a new channel (email, Discord) |
| `send_message` | Sends a new outbound message on a given channel |
| `reply` | Replies within an existing conversation thread |
| `get_new_messages` | Drains the buffered inbound message queue |
| `get_conversation` | Retrieves the full message history for a given conversation ID |

**Bridging Caspian's `listen()` model to MCP's request/response model:** Caspian's SDK is built around a blocking `client.listen()` loop that fires `on_message` per inbound message. Since MCP tools are request/response rather than long-running, the MCP server runs `client.listen()` in a background thread at startup, and inbound messages are buffered into an in-memory queue that `get_new_messages` drains on demand.

---

## 6. Gateway Choice: Hosted, Not Self-Hosted

Caspian offers both a hosted gateway (`api.trycaspianai.com`) and a self-hostable version of the same FastAPI gateway (AGPL-3.0-or-later licensed, in `server/` of the SDK repo).

**Decision: use the hosted gateway.**

| Consideration | Hosted (chosen) | Self-hosted |
|---|---|---|
| Setup time | Zero — `caspian init`, connect channels, done | Docker + own Postgres + public tunnel for webhooks |
| Infra overhead | None | Requires maintaining a running service for 15 days |
| Demo proof | Free dashboard showing live stats (bots live, conversations, messages, cost) — strong proof-of-liveness for the required demo video | Would need custom observability built from scratch |
| Data custody | Caspian's infrastructure handles message transport | Full control over the message store |

Given the 15-day timeline and that FirstCall's actual security commitment is about **candidate PII and screening data that *FirstCall itself* stores** (not the transport layer), self-hosting the gateway wasn't necessary to meet the security goals below. Security is instead implemented at the MCP server's own storage layer.

---

## 7. Security & Data Protection

Security was treated as a first-class requirement throughout the design, not a bolt-on.

### 7.1 Encryption at rest
All candidate data — screening transcripts, chat history, resumes, phone numbers, addresses — is encrypted at the storage layer (field-level encryption, e.g. via `cryptography`'s Fernet), not merely relying on disk-level or database-level encryption.

### 7.2 Access control
Strict per-candidate/per-conversation isolation: one HR account/business can never query another's candidate pipeline or conversation history, even via a malformed request. This is tested explicitly (see §9). Enforcement is keyed off a real authenticated identity — see §7.2.1 — rather than a client-supplied identifier.

### 7.2.1 Authentication (Auth0)

The HR dashboard is protected by **Auth0**, chosen because the team had prior working experience with it from another project, minimizing setup risk in a 15-day window.

- **Provider:** Auth0 (development tenant is sufficient at hackathon scale — no separate production tenant needed)
- **Scope of protection:** only the HR dashboard sits behind authentication. The public landing page (job listings, application form) remains fully open — candidates never need an account.
- **Frontend:** the React dashboard uses the `@auth0/auth0-react` SDK for the login/redirect flow — no custom login form, password reset, or email verification is built.
- **Backend:** FastAPI verifies Auth0-issued JWTs on incoming requests by validating them against Auth0's JWKS (JSON Web Key Set) endpoint. No custom session or JWT signing logic is implemented — Auth0 is the sole source of truth for identity.
- **Data model impact:** a new `business` entity is introduced, keyed off the Auth0 user's `sub` (unique subject identifier). Every job posting, candidate, and conversation record carries a `business_id` foreign key.
- **Why this matters for security:** this `business_id`, derived from a verified Auth0 session rather than any client-supplied value, is exactly what the access-control tests (§9) check against — a request for another business's candidate data is rejected because the authenticated `business_id` doesn't match the record being requested, not because of a trust-based check on data the client could forge.

### 7.3 Secrets management
API keys (Caspian, Discord bot token, SMTP credentials) are never logged, never committed, and stored via environment variables (`.env`, excluded from version control) or the deployment platform's secret store.

### 7.4 Audit trail
A separate, append-only log records **who accessed which candidate's data, and when** — distinct from general operational logging (§8). This is a backend-only concern for the MVP; no dedicated audit log UI was built, to keep the frontend scope slim.

### 7.5 What is explicitly out of scope
- No resume auto-parsing/reading by an LLM in the MVP — resumes are stored as plain downloadable files
- No voice/audio interview recording — text-only screening; audio would require a separate speech-to-text pipeline outside Caspian's scope and was judged too large a risk to attempt in 15 days (listed as a roadmap item instead)
- No adaptive/dynamic interview questioning — the screening question set is fixed per job, not dynamically generated per candidate (also a roadmap item)

---

## 8. Logging

Structured, extensive logging is implemented across all Python services, distinct from — and never overlapping with — the encrypted PII store.

- **Library:** `structlog` (or Python's standard `logging` with a JSON formatter)
- **Correlation IDs:** every log line carries a `conversation_id`/`request_id`, allowing a single candidate's entire journey (application received → FAQ answered → screening assigned → answers submitted → HR reviewed) to be traced as one connected sequence
- **Log levels:**
  - `INFO` — every significant event (message received, MCP tool invoked, pipeline stage transition, email sent)
  - `DEBUG` — verbose, development-only detail
  - `WARNING` / `ERROR` — failures, retries, encryption/decryption errors, auth failures
- **Critical rule:** logs record *metadata about* events, never raw PII or message content in plaintext. For example:
  - ✅ `{"event": "screening_answer_received", "candidate_id": "abc123", "question_index": 3, "channel": "discord"}`
  - ❌ Logging the literal candidate answer text
- **Destination:** stdout only, captured automatically by the deployment platform (Railway/Docker). No dedicated log aggregation service (e.g. Datadog) is used, given hackathon scale and timeline.

---

## 9. Testing Strategy

- **Tests-first implementation** of each MCP tool before moving to the next
- **Access-control tests** — explicit tests that attempt to read another business's candidate/conversation data and assert failure
- **Real, not mocked, integration test** — a genuine Email + Discord round-trip through the live handler, in line with the hackathon's requirement that demo videos show real, unmocked functionality
- **Cost-control tests** — verifying LLM calls only occur where intended (FAQ answering, on-demand AI review) and never per-message or automatically per-candidate

### 9.1 Continuous Integration

`.github/workflows/ci.yml` runs on every push/PR to `master` as three independent jobs:

| Job | Scope | Steps |
|---|---|---|
| `js` | `apps/dashboard`, `apps/landing` | `pnpm install --frozen-lockfile`, then `pnpm turbo run lint build test` |
| `mcp-server` | `services/mcp-server` | `uv sync`, `uv run ruff check .`, `uv run pytest` |
| `backend` | `services/backend` | `uv sync`, `uv run ruff check .`, `uv run pytest` |

All three must pass before a PR is considered mergeable. Locally, run the same checks any job runs before pushing:
```
pnpm turbo run lint build test --filter=dashboard --filter=landing
cd services/mcp-server && uv run ruff check . && uv run pytest
cd services/backend && uv run ruff check . && uv run pytest
```

---

## 10. Cost Minimization

Given the security/testing investment, LLM and infrastructure cost was deliberately minimized elsewhere:

- **Model:** Claude Haiku for all LLM calls (FAQ answering, on-demand AI review) — no Sonnet/Opus usage
- **Call frequency:** LLM invoked only for FAQ-answering and *on-demand* AI review — never automatically per candidate, never per-message
- **Prompting:** short, static system prompt per job (the job description + FAQ doc), not a large or dynamically rebuilt context; capped `max_tokens` on all calls
- **Database:** SQLite, not Postgres — sufficient at hackathon scale, avoids a managed database cost
- **Hosting:** Railway free tier for the demo deployment
- **Channels:** Email and Discord only — both free on Caspian's hosted gateway; no SMS or other paid channels

---

## 11. Monorepo Structure & Tech Stack

FirstCall uses a **hybrid monorepo** — not a pure Turborepo setup — because the codebase spans both native TypeScript apps and Python services, and Turborepo does not natively understand Python's dependency graph.

```
firstcall/
├── apps/
│   ├── dashboard/          # React + Vite + Shadcn + TailwindCSS — HR-facing
│   └── landing/             # React + Vite + Shadcn + TailwindCSS — public job postings
├── services/
│   ├── mcp-server/          # Python — caspian-sdk wrapper, MCP tool definitions
│   └── backend/             # Python (FastAPI) — API for dashboard + landing page
├── docker-compose.yml        # Runs mcp-server + backend (+ SQLite volume)
├── turbo.json                 # Orchestrates apps/* only
├── package.json                # pnpm workspaces: ["apps/*"]
├── Makefile                    # `make dev` = docker compose up -d + turbo dev --filter=dashboard --filter=landing
├── .env.example
└── README.md
```

**Rationale for the split:**
- `apps/` (dashboard, landing) — React + Vite + Shadcn + TailwindCSS, genuinely native JS/TS packages, managed by **Turborepo** for unified `dev`/`build`/`test` commands and real build caching
- `services/` (mcp-server, backend) — Python, managed via **Docker Compose** rather than forced into Turborepo's JS-centric task model, avoiding fragile caching behavior on a dependency graph Turborepo can't natively read
- A root **Makefile** unifies both halves under one command (`make dev`) so the whole stack starts together during development

**One GitHub repository** houses all of the above, per the hackathon's one-submission-per-team rule. The README explicitly states which handler (Agent 1) satisfies the two-channel qualification requirement, to remove any ambiguity for judges reviewing a two-agent, multi-app submission.

---

## 12. Reference Implementations Used

FirstCall's initial scaffolding is based on maintainer-provided templates rather than built from a blank repository:

- **`TryCaspian/railway-ai-agent-template`** — a working Email + Telegram + Discord agent deployable to Railway in one click; used as the base for Agent 1's handler structure
- **`TryCaspian/discord-ai-agent-template`** — Discord-specific reference implementation

A live email round-trip (candidate email → agent FAQ auto-response) was validated early via the hosted gateway, confirmed in both the recipient's inbox and Caspian's own dashboard — establishing that the core SDK integration works end-to-end before further build-out.

---

## 13. Roadmap (Explicitly Out of Scope for the Hackathon MVP)

- Voice/audio-based screening (would require a speech-to-text pipeline; no viable free option identified)
- Adaptive/dynamic interview questioning based on candidate responses
- Resume parsing/reading by an LLM
- A knowledge-base editor UI (currently a config file)
- An audit-log viewer UI (currently backend-only)

---

## 14. Hackathon Compliance Summary

| Requirement | How FirstCall satisfies it |
|---|---|
| Uses `caspian-sdk` | Both agents built directly on the Python SDK |
| Runs on ≥2 supported channels via one handler | Agent 1 operates on Email + Discord through a single `on_message` handler |
| Public GitHub repository | Single monorepo housing both agents, MCP server, backend, and both frontend apps |
| Demo video shows real functionality | Live, unmocked Email + Discord round-trip; Caspian's own dashboard used as corroborating proof of real activity |
| Creativity/originality | Novel MCP server built on top of the SDK (a feature not yet shipped by Caspian itself); escalation-aware, security-first design tailored to an underserved small-business hiring segment |
