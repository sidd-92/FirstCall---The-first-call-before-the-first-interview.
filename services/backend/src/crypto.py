"""Decrypt Fernet-encrypted message content (see models.py's
Message.content_encrypted). Shares ENCRYPTION_KEY with services/mcp-server,
which is what actually writes these rows -- this backend never encrypts
message content itself, only reads it back for HR-facing views.
"""

import os
from functools import lru_cache

from cryptography.fernet import Fernet


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not set -- required to read message content.")
    return Fernet(key)


def decrypt_content(content_encrypted: bytes) -> str:
    return _fernet().decrypt(content_encrypted).decode("utf-8")
