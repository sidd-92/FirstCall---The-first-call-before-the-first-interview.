"""Shared test fixtures: a throwaway SQLite DB with the real shared schema
(mirrors services/backend/src/models.py -- kept minimal/hand-written here
since mcp-server can't import backend's package; see src/db.py's docstring),
wired up so src.db and src.storage transparently use it instead of the real
DATABASE_URL.
"""


import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

_SCHEMA = """
CREATE TABLE businesses (
    id INTEGER PRIMARY KEY,
    auth0_sub VARCHAR UNIQUE,
    name VARCHAR,
    created_at DATETIME
);

CREATE TABLE job_postings (
    id INTEGER PRIMARY KEY,
    business_id INTEGER REFERENCES businesses(id),
    title VARCHAR,
    description TEXT,
    faq_json TEXT,
    is_active BOOLEAN,
    created_at DATETIME
);

CREATE TABLE candidates (
    id INTEGER PRIMARY KEY,
    business_id INTEGER REFERENCES businesses(id),
    job_posting_id INTEGER REFERENCES job_postings(id),
    name VARCHAR,
    email VARCHAR,
    phone VARCHAR,
    address VARCHAR,
    resume_file_path VARCHAR,
    discord_user_id VARCHAR UNIQUE,
    created_at DATETIME
);

CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER REFERENCES candidates(id),
    channel VARCHAR,
    external_conversation_id VARCHAR UNIQUE,
    created_at DATETIME
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    direction VARCHAR,
    content_encrypted BLOB,
    kind VARCHAR,
    created_at DATETIME
);

CREATE TABLE pipeline_stages (
    candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id),
    stage VARCHAR,
    updated_at DATETIME
);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh SQLite file per test, with the shared schema applied, and
    src.db/src.storage pointed at it. Returns the `src.db` module so tests
    can seed rows via `db.engine` directly."""
    import src.db as db_module

    db_path = tmp_path / "test.db"
    test_engine = create_engine(f"sqlite:///{db_path}")
    with test_engine.begin() as conn:
        for statement in _SCHEMA.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    return db_module


def seed_business(db_module, business_id: int = 1) -> None:
    with db_module.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO businesses (id, auth0_sub, name, created_at) "
                "VALUES (:id, :sub, :name, datetime('now'))"
            ),
            {"id": business_id, "sub": f"auth0|{business_id}", "name": "Acme Co"},
        )


def seed_job_posting(
    db_module,
    job_posting_id: int = 1,
    business_id: int = 1,
    faq_json: str = "{}",
    title: str = "Barista",
    description: str = "Make coffee, delight customers.",
) -> None:
    with db_module.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job_postings "
                "(id, business_id, title, description, faq_json, is_active, created_at) "
                "VALUES (:id, :business_id, :title, :description, :faq_json, 1, datetime('now'))"
            ),
            {
                "id": job_posting_id,
                "business_id": business_id,
                "title": title,
                "description": description,
                "faq_json": faq_json,
            },
        )


def seed_candidate(
    db_module,
    candidate_id: int = 1,
    business_id: int = 1,
    job_posting_id: int = 1,
    email: str = "candidate@example.com",
    discord_user_id: str | None = None,
) -> None:
    with db_module.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO candidates "
                "(id, business_id, job_posting_id, name, email, phone, address, "
                "resume_file_path, discord_user_id, created_at) "
                "VALUES (:id, :business_id, :job_posting_id, 'Jamie Doe', :email, "
                "'555-0100', '123 Main St', '/resumes/jamie.pdf', :discord_user_id, "
                "datetime('now'))"
            ),
            {
                "id": candidate_id,
                "business_id": business_id,
                "job_posting_id": job_posting_id,
                "email": email,
                "discord_user_id": discord_user_id,
            },
        )


def seed_pipeline_stage(db_module, candidate_id: int = 1, stage: str = "applied") -> None:
    with db_module.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pipeline_stages (candidate_id, stage, updated_at) "
                "VALUES (:candidate_id, :stage, datetime('now'))"
            ),
            {"candidate_id": candidate_id, "stage": stage},
        )
