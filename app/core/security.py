"""
Password hashing + JWT creation/validation.

JAVA: PasswordEncoder (BCryptPasswordEncoder) + a JwtService using jjwt.
This file holds NO framework code - it is pure crypto logic, so it is trivial
to unit test.
"""

import hashlib
import secrets
import uuid
from datetime import timezone, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

# bcrypt only looks at the first 72 BYTES of a password and bcrypt>=4.1 raises
# on longer input. We enforce max length in the schema too, but this is the
# safety net.
BCRYPT_MAX_BYTES = 72


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """JAVA: passwordEncoder.encode(raw)"""
    pw = plain.encode("utf-8")[:BCRYPT_MAX_BYTES]
    # rounds=12 is the current sane default: ~250ms per hash. Slow ON PURPOSE.
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """JAVA: passwordEncoder.matches(raw, encoded)"""
    try:
        pw = plain.encode("utf-8")[:BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except ValueError:
        # malformed hash in the DB - treat as "wrong password", never crash
        return False


# ---------------------------------------------------------------------------
# JWT
#
# An access token is a signed JSON blob. The server does NOT store it and
# CANNOT revoke it - that is why it expires in 15 minutes.
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)      # always UTC. never datetime.now().


def create_access_token(subject: str, role: str) -> str:
    s = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": subject,                                   # who
        "role": role,                                     # what they may do
        "type": "access",                                 # see decode_token()
        "iat": now,                                       # issued at
        "exp": now + timedelta(minutes=s.access_token_minutes),
        "jti": str(uuid.uuid4()),                         # unique token id
    }
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm)


def create_refresh_token() -> tuple[str, str, datetime]:
    """
    Returns (raw_token, sha256_of_token, expires_at).

    The refresh token is a random string, NOT a JWT - it only needs to be
    unguessable. We store only its SHA-256 in the database, exactly like a
    password: a leaked DB dump then contains no usable tokens.
    """
    raw = secrets.token_urlsafe(48)
    expires = _now() + timedelta(days=get_settings().refresh_token_days)
    return raw, hash_token(raw), expires


def hash_token(raw: str) -> str:
    # sha256 (not bcrypt) because this runs on every refresh and the input is
    # already 48 random bytes - there is nothing to brute force.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TokenError(Exception):
    """Raised for any invalid token. The API layer turns this into a 401."""


def decode_access_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise TokenError("Token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("Invalid token") from e

    # A refresh token must never be accepted as an access token.
    # Skipping this check is a real, common vulnerability.
    if payload.get("type") != "access":
        raise TokenError("Wrong token type")

    return payload


# ---------------------------------------------------------------------------
# API keys (for machine clients that cannot do a login flow)
# ---------------------------------------------------------------------------

def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key_shown_once, sha256_stored_in_db)."""
    raw = "faq_" + secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def constant_time_equals(a: str, b: str) -> bool:
    """
    JAVA: MessageDigest.isEqual(...)
    `a == b` leaks how many characters matched via timing. Never compare
    secrets with ==.
    """
    return secrets.compare_digest(a, b)
