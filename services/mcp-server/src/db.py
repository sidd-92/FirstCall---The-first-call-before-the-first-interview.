"""Read/write access to the SQLite database shared with services/backend.

services/backend/src/models.py owns the canonical schema (see the earlier
decision to share one SQLite file rather than run two databases). mcp-server
is a separate uv project/container, so importing backend's SQLAlchemy models
directly isn't practical -- instead this module declares plain SQLAlchemy
Core `Table` objects for just the columns Agent 1 actually reads or writes.

These column definitions MUST be kept in sync with backend/src/models.py by
hand. This duplication is a known tradeoff for the hackathon; extracting a
shared schema package is the natural follow-up once there's a third
consumer.
"""

import os
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./firstcall.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

metadata = MetaData()

job_postings = Table(
    "job_postings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("business_id", Integer),
    Column("title", String),
    Column("description", String),
    Column("faq_json", String),
)

candidates = Table(
    "candidates",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("business_id", Integer),
    Column("job_posting_id", Integer, ForeignKey("job_postings.id")),
    Column("email", String),
    Column("discord_user_id", String),
)

pipeline_stages = Table(
    "pipeline_stages",
    metadata,
    Column("candidate_id", Integer, primary_key=True),
    Column("stage", String),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("candidate_id", Integer, ForeignKey("candidates.id")),
    Column("channel", String),
    Column("external_conversation_id", String),
    Column("created_at", DateTime),
)

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("conversation_id", Integer, ForeignKey("conversations.id")),
    Column("direction", String),
    Column("content_encrypted", LargeBinary),
    Column("kind", String),
    Column("created_at", DateTime),
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def get_candidate(candidate_id: int) -> dict | None:
    stmt = select(
        candidates.c.id, candidates.c.business_id, candidates.c.job_posting_id
    ).where(candidates.c.id == candidate_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
    return row._asdict() if row else None


def find_candidate_by_email(email: str, job_posting_id: int | None = None) -> dict | None:
    """Match a candidate by application email, optionally scoped to a job posting
    (disambiguates the same person applying to multiple postings)."""
    stmt = select(
        candidates.c.id, candidates.c.business_id, candidates.c.job_posting_id
    ).where(candidates.c.email == email)
    if job_posting_id is not None:
        stmt = stmt.where(candidates.c.job_posting_id == job_posting_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
    return row._asdict() if row else None


def find_candidate_by_discord_user_id(discord_user_id: str) -> dict | None:
    stmt = select(
        candidates.c.id, candidates.c.business_id, candidates.c.job_posting_id
    ).where(candidates.c.discord_user_id == discord_user_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
    return row._asdict() if row else None


def get_job_posting(job_posting_id: int) -> dict | None:
    stmt = select(
        job_postings.c.id,
        job_postings.c.business_id,
        job_postings.c.title,
        job_postings.c.description,
        job_postings.c.faq_json,
    ).where(job_postings.c.id == job_posting_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
    return row._asdict() if row else None


def get_pipeline_stage(candidate_id: int) -> str | None:
    stmt = select(pipeline_stages.c.stage).where(pipeline_stages.c.candidate_id == candidate_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
    return row.stage if row else None


def find_conversation_by_external_id(external_conversation_id: str) -> dict | None:
    stmt = select(conversations.c.id, conversations.c.candidate_id, conversations.c.channel).where(
        conversations.c.external_conversation_id == external_conversation_id
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
    return row._asdict() if row else None


def create_conversation(candidate_id: int, channel: str, external_conversation_id: str) -> int:
    stmt = insert(conversations).values(
        candidate_id=candidate_id,
        channel=channel,
        external_conversation_id=external_conversation_id,
        created_at=_utcnow(),
    )
    with engine.begin() as conn:
        result = conn.execute(stmt)
        return result.inserted_primary_key[0]


def count_messages_by_kind(conversation_id: int, kind: str) -> int:
    stmt = select(messages.c.id).where(
        messages.c.conversation_id == conversation_id, messages.c.kind == kind
    )
    with engine.connect() as conn:
        return len(conn.execute(stmt).all())
