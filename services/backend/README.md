# backend

FastAPI service — serves the public landing-page API (job postings, applications) and
the Auth0-authenticated HR dashboard API (candidate pipeline, screening review).

## Dev setup

```bash
uv sync
uv run uvicorn src.main:app --reload
```

## Layout

- `src/main.py` — FastAPI app entrypoint, mounts `routes/public.py` and `routes/dashboard.py`
- `src/models.py` — SQLAlchemy models
- `src/auth.py` — Auth0 JWT verification via JWKS, `get_current_business` dependency
- `src/routes/public.py` — unauthenticated job listing / application endpoints
- `src/routes/dashboard.py` — authenticated candidate pipeline endpoints
- `src/logging_config.py` — structlog JSON logging setup
- `tests/` — pytest suite
