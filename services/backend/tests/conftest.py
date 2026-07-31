"""Test-session setup: point the app at a throwaway SQLite file instead of
the real DATABASE_URL, before src.main (and therefore src.db) ever gets
imported by a test module. python-dotenv's load_dotenv() (called in
src.main) never overrides an already-set env var, so setting these here
first keeps tests isolated from a real local .env.
"""

import os
import tempfile

from cryptography.fernet import Fernet

_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
os.environ["RESUME_STORAGE_DIR"] = f"{_tmp_dir}/resumes"
os.environ.setdefault("AUTH0_DOMAIN", "test.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://test-audience")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("CASPIAN_API_KEY", "test-caspian-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

import pytest

from src.db import engine
from src.models import Base

Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    from src.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
