"""Password hashing and JWT helpers.

Kept as plain functions (no classes) per project convention — this module
is imported by services, never the other way around, so there's no risk of
circular imports.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_token(
    *, subject: str, token_type: TokenType, tenant_id: str | None = None, extra_claims: dict | None = None
) -> str:
    """Create a signed JWT.

    `subject` is the user id. Access tokens optionally carry a `tenant_id`
    claim identifying which tenant the session is currently acting as
    (a user can belong to several tenants; the active one is chosen at
    login/switch time and baked into the token so every request is
    unambiguously scoped without a lookup).
    """
    now = datetime.now(timezone.utc)
    if token_type == "access":
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "sub", "jti"], "verify_signature": True},
        )
    except JWTError:
        return None


def generate_secret_token(nbytes: int = 32) -> str:
    """URL-safe random token used for invitations, password resets, etc."""
    return secrets.token_urlsafe(nbytes)


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns (plaintext_key, key_prefix, hashed_key). Only the hash is ever
    persisted; the plaintext is returned once to the caller to show the user.
    """
    raw = secrets.token_urlsafe(32)
    plaintext_key = f"fd_live_{raw}"
    key_prefix = plaintext_key[:12]
    hashed_key = hash_api_key(plaintext_key)
    return plaintext_key, key_prefix, hashed_key


def hash_api_key(plaintext_key: str) -> str:
    return hashlib.sha256(plaintext_key.encode()).hexdigest()


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)


def sign_webhook_payload(secret: str, payload_bytes: bytes) -> str:
    return hashlib.sha256(secret.encode() + payload_bytes).hexdigest()
