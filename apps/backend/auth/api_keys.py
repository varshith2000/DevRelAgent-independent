"""Project-scoped API keys.

Format: ``drk_<prefix>_<secret>``. Only a salted hash of the full key is
stored, plus the short prefix in clear so verification is one indexed lookup
followed by a constant-time comparison.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

from config.settings import get_settings
from db.models import ApiKey
from sqlalchemy import select
from sqlalchemy.orm import Session

KEY_BASE = "drk_"
_PREFIX_BYTES = 6  # -> 12 hex characters


def hash_key(plaintext: str) -> str:
    """Hash a key for storage/comparison, salted with the configured pepper."""
    pepper = get_settings().api_key_pepper or ""
    return hashlib.sha256(f"{pepper}{plaintext}".encode()).hexdigest()


def generate_key() -> Tuple[str, str, str]:
    """Create a new key.

    Returns ``(plaintext, prefix, key_hash)``. The plaintext is only available
    here and must be shown to the user once.
    """
    prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_urlsafe(32)
    plaintext = f"{KEY_BASE}{prefix}_{secret}"
    return plaintext, prefix, hash_key(plaintext)


def parse_prefix(plaintext: str) -> Optional[str]:
    """Extract the lookup prefix, or ``None`` if the key is malformed."""
    if not plaintext.startswith(KEY_BASE):
        return None
    remainder = plaintext[len(KEY_BASE) :]
    prefix, separator, _ = remainder.partition("_")
    if not separator or not prefix:
        return None
    return prefix


def resolve_api_key(session: Session, plaintext: str) -> Optional[ApiKey]:
    """Return the active API key matching ``plaintext``, if any."""
    prefix = parse_prefix(plaintext)
    if prefix is None:
        return None

    key = session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if key is None or not key.is_active:
        return None
    if not secrets.compare_digest(key.key_hash, hash_key(plaintext)):
        return None

    key.last_used_at = datetime.now(timezone.utc)
    session.commit()
    return key
