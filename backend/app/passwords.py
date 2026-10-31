"""
app/passwords.py — password hashing for web (non-Telegram) accounts.

Uses the standard library only: hashlib.scrypt is a memory-hard KDF designed
for exactly this, so we add no dependency (bcrypt/argon2 are not installed).

Stored format (single column, future-proof):
    scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>
Parameters are embedded so older hashes stay verifiable if we raise them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# OWASP-recommended scrypt baseline (N=2^14, r=8, p=1).
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a plain password (never store or log the input)."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. A missing/garbled hash simply never matches."""
    if not stored:
        return False
    try:
        scheme, n_s, r_s, p_s, salt_s, hash_s = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_s),
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(_unb64(hash_s)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, _unb64(hash_s))
