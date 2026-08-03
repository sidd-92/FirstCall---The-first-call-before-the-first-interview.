"""FastAPI app entrypoint for the FirstCall backend."""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

load_dotenv()

from src.db import engine
from src.logging_config import configure_logging, get_logger
from src.models import Base
from src.routes import businesses, dashboard, public

configure_logging()
log = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: replace create_all with Alembic migrations once the schema
    # stabilizes -- fine for hackathon/SQLite bring-up for now.
    Base.metadata.create_all(bind=engine)
    # create_all() only creates missing tables, never adds columns to ones
    # that already exist -- a hand-rolled, idempotent patch for columns added
    # after a dev DB file was first created. Same hackathon-grade tradeoff as
    # create_all() above; drop once real migrations land.
    with engine.begin() as conn:
        try:
            conn.execute(
                text("ALTER TABLE conversations ADD COLUMN is_dm BOOLEAN NOT NULL DEFAULT 0")
            )
        except OperationalError:
            pass  # column already exists
    log.info("backend_starting")
    yield


# The landing and dashboard apps are separate Vite dev servers (different
# origins/ports) hitting this API directly from the browser -- without CORS
# the browser blocks every request before it reaches a route. Configurable
# via CORS_ALLOWED_ORIGINS (comma-separated) since the dashboard's real prod
# origin isn't known yet; defaults cover local Vite dev.
_default_origins = "http://localhost:5173,http://localhost:5174"
allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", _default_origins).split(",")

app = FastAPI(title="FirstCall Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public.router)
app.include_router(dashboard.router)
app.include_router(businesses.router)


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(request: Request, exc: NotImplementedError) -> JSONResponse:
    # Many routes are still stubs (raise NotImplementedError). An *unhandled*
    # exception unwinds past CORSMiddleware without it attaching CORS headers
    # to the resulting 500 -- the browser then reports a misleading "CORS
    # policy" error that hides the real 501. Handling it here keeps the
    # response inside the middleware stack so CORS headers still get added.
    return JSONResponse(status_code=501, content={"detail": "Not implemented yet"})


@app.get("/health")
def health():
    return {"status": "ok"}
