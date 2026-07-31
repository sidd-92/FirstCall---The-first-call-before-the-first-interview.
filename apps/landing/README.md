# landing

Public-facing app for browsing job postings and applying — no authentication. React + Vite +
TypeScript, Shadcn/ui, Tailwind CSS.

## Dev setup

```bash
cp .env.example .env.local
pnpm install
pnpm dev
```

## Pages

- `/` — list of open job postings, fetched from `GET /jobs` on the backend
- `/jobs/:id` — full job detail + an application form that `POST`s multipart/form-data to
  `POST /jobs/:id/apply`; on success, shows a "Copy application email" button that copies a
  `mailto:` link pre-filled with the agent's email and a subject line tagging the job id

## Env vars

See `.env.example` — `VITE_API_BASE_URL` (backend base URL) and `VITE_AGENT_EMAIL_ADDRESS`
(used to build the mailto link).
