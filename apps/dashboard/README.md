# dashboard

Authenticated HR-facing app for managing the hiring pipeline. React + Vite + TypeScript,
Shadcn/ui, Tailwind CSS, protected by Auth0.

## Dev setup

```bash
cp .env.example .env.local
pnpm install
pnpm dev
```

## Auth

Every route is wrapped in `withAuthenticationRequired` (see `src/components/ProtectedRoute.tsx`)
and redirects to Auth0 login when unauthenticated. Once logged in, `useAuthedApi`
(`src/lib/useAuthedApi.ts`) fetches a fresh access token via `getAccessTokenSilently` and attaches
it as `Authorization: Bearer <token>` on every backend call.

## Pages

- `/` — candidate pipeline: name, job posting, stage, last activity. `GET /candidates`
- `/candidates/:id` — application info + resume link, chat/email history, screening transcript
  (if completed), "Review with AI", "Assign Screening" (if not yet assigned), "Shortlist for Next
  Round" (if screening completed)
- `/interviews` — upcoming interviews list

## Env vars

See `.env.example` — `VITE_API_BASE_URL`, and the Auth0 SPA app's `VITE_AUTH0_DOMAIN` /
`VITE_AUTH0_CLIENT_ID` / `VITE_AUTH0_AUDIENCE` (audience must match the backend's `AUTH0_AUDIENCE`
so the access token is a verifiable JWT, not an opaque token).
