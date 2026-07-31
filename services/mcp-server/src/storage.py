"""Conversation/candidate storage interface.

Backing store will be SQLite. Message CONTENT will be encrypted at rest
using `cryptography`'s Fernet symmetric encryption (key sourced from env)
before this is implemented -- do not store plaintext message bodies.

Every query will also be scoped by a `business_id` field once Auth0 /
the business entity model is wired in on the backend (later prompt). Until
then, signatures below accept `business_id` so callers already pass it and
we don't have to touch call sites again when scoping is enforced.
"""

from dataclasses import dataclass


@dataclass
class Message:
    """A single message within a conversation."""

    conversation_id: str
    business_id: str
    channel: str
    content: str
    direction: str  # "inbound" | "outbound"


def get_message(business_id: str, message_id: str) -> Message | None:
    """Fetch a single message by id, scoped to business_id.

    TODO: implement SQLite lookup + Fernet decryption of `content`.
    """
    raise NotImplementedError


def save_message(message: Message) -> None:
    """Persist a message.

    TODO: implement SQLite insert + Fernet encryption of `content` before
    writing to disk.
    """
    raise NotImplementedError


def get_conversation(business_id: str, conversation_id: str) -> list[Message]:
    """Fetch all messages in a conversation, scoped to business_id, in order.

    TODO: implement SQLite query + Fernet decryption of each message's
    `content`.
    """
    raise NotImplementedError
