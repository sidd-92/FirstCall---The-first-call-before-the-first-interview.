"""Conversation/candidate message storage.

Message CONTENT is encrypted at rest using `cryptography`'s Fernet symmetric
encryption (key from the ENCRYPTION_KEY env var, shared with
services/backend) -- callers only ever see/pass plaintext; encryption and
decryption happen at this boundary and nowhere else.

Reads/writes go through src/db.py's Core `Table` objects against the same
SQLite file services/backend owns (see db.py's docstring on why the schema
is duplicated there rather than imported).
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from cryptography.fernet import Fernet
from sqlalchemy import select

from src import db


@dataclass
class Message:
    """A single message within a conversation (plaintext -- decrypted, if read)."""

    id: int | None
    conversation_id: int
    direction: str  # "inbound" | "outbound"
    content: str
    kind: str | None = None
    created_at: datetime | None = None


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set -- required to read/write message content. "
            "Generate one with: python -c "
            "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key)


def _row_to_message(row) -> Message:
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        direction=row.direction,
        content=_fernet().decrypt(row.content_encrypted).decode("utf-8"),
        kind=row.kind,
        created_at=row.created_at,
    )


def save_message(
    conversation_id: int, direction: str, content: str, kind: str | None = None
) -> int:
    """Encrypt and persist a message. Returns the new message id."""
    content_encrypted = _fernet().encrypt(content.encode("utf-8"))
    stmt = db.messages.insert().values(
        conversation_id=conversation_id,
        direction=direction,
        content_encrypted=content_encrypted,
        kind=kind,
        created_at=datetime.now(UTC),
    )
    with db.engine.begin() as conn:
        result = conn.execute(stmt)
        return result.inserted_primary_key[0]


def get_message(message_id: int) -> Message | None:
    """Fetch a single message by id, decrypted."""
    stmt = select(db.messages).where(db.messages.c.id == message_id)
    with db.engine.connect() as conn:
        row = conn.execute(stmt).first()
    return _row_to_message(row) if row else None


def get_conversation(conversation_id: int) -> list[Message]:
    """Fetch all messages in a conversation, decrypted, oldest first."""
    stmt = (
        select(db.messages)
        .where(db.messages.c.conversation_id == conversation_id)
        .order_by(db.messages.c.id)
    )
    with db.engine.connect() as conn:
        rows = conn.execute(stmt).all()
    return [_row_to_message(row) for row in rows]
