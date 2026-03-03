"""
Security utilities — API key generation, hashing, brute-force protection.
"""

import hashlib
import secrets
import time
from collections import defaultdict
from typing import Optional

from app.config import settings


# ── In-memory brute-force tracker ────────────────
_failed_attempts: dict = defaultdict(list)  # ip -> [timestamps]


def generate_api_key() -> str:
    """Generate a cryptographically secure API key (shown only once)."""
    return secrets.token_urlsafe(settings.API_KEY_LENGTH)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash an API key for secure storage."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key_hash(raw_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against its stored hash."""
    return hash_api_key(raw_key) == stored_hash


# ── Brute-Force Protection ───────────────────────

def record_failed_attempt(identifier: str):
    """Record a failed authentication attempt."""
    now = time.time()
    _failed_attempts[identifier].append(now)
    # Cleanup old entries
    cutoff = now - (settings.LOCKOUT_MINUTES * 60)
    _failed_attempts[identifier] = [
        t for t in _failed_attempts[identifier] if t > cutoff
    ]


def is_locked_out(identifier: str) -> bool:
    """Check if an identifier is locked out due to too many failed attempts."""
    now = time.time()
    cutoff = now - (settings.LOCKOUT_MINUTES * 60)
    recent = [t for t in _failed_attempts.get(identifier, []) if t > cutoff]
    return len(recent) >= settings.MAX_FAILED_ATTEMPTS


def clear_failed_attempts(identifier: str):
    """Clear failed attempts after successful auth."""
    _failed_attempts.pop(identifier, None)
