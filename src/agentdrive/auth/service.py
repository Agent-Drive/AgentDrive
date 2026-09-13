import secrets
import string

import bcrypt

KEY_PREFIX = "sk-ad-"
PREFIX_LENGTH = 8
KEY_RANDOM_LENGTH = 32

_ALPHABET = string.ascii_letters + string.digits


def hash_api_key(key: str) -> str:
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(key: str, hashed: str) -> bool:
    return bcrypt.checkpw(key.encode(), hashed.encode())


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, prefix, key_hash) — raw_key shown once, prefix stored plaintext, hash stored.
    """
    random_part = "".join(secrets.choice(_ALPHABET) for _ in range(KEY_RANDOM_LENGTH))
    prefix = random_part[:PREFIX_LENGTH]
    raw_key = f"{KEY_PREFIX}{random_part}"
    key_hash = hash_api_key(raw_key)
    return raw_key, prefix, key_hash


def parse_key_prefix(key: str) -> str | None:
    """Extract the 8-char prefix from an sk-ad- key. Returns None for legacy keys."""
    if not key.startswith(KEY_PREFIX):
        return None
    remainder = key[len(KEY_PREFIX):]
    if len(remainder) < PREFIX_LENGTH:
        return None
    return remainder[:PREFIX_LENGTH]
