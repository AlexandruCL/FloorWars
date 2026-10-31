"""One-time sign-in codes (plan 7.9): 6 digits from ``secrets``, stored as ``sha256(salt || code)``.

The salt is 16 random bytes per challenge. Comparison is constant-time. The code itself exists
only in memory between generation and the mail backend; it is never stored, logged or returned.
"""

import hashlib
import hmac
import secrets

CODE_DIGITS = 6
SALT_BYTES = 16


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def new_salt() -> bytes:
    return secrets.token_bytes(SALT_BYTES)


def hash_code(salt: bytes, code: str) -> bytes:
    return hashlib.sha256(salt + code.encode("ascii")).digest()


def code_matches(salt: bytes, code: str, expected_hash: bytes) -> bool:
    return hmac.compare_digest(hash_code(salt, code), expected_hash)
