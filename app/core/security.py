"""Security utilities: API Key hashing (SHA-256), generation, and JWT validation."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from jose import jwt, JWTError

from app.config import settings
from app.core.exceptions import AuthenticationException


def hash_api_key(raw_key: str) -> str:
    """Hash raw API key using SHA-256.

    Args:
        raw_key: Plaintext API key provided by the client.

    Returns:
        64-character hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def generate_api_key(prefix: str = "af_live_") -> Tuple[str, str, str]:
    """Generate a cryptographically secure random API key.

    Returns:
        Tuple of (raw_key, hashed_key, key_prefix).
        Example raw_key: 'af_live_8f3a1b...'
        Example key_prefix: 'af_live_8f3a'
    """
    token = secrets.token_hex(24)  # 48 characters
    raw_key = f"{prefix}{token}"
    hashed = hash_api_key(raw_key)
    short_prefix = raw_key[:12]
    return raw_key, hashed, short_prefix


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of hashed API keys to prevent timing attacks.

    Args:
        raw_key: User provided raw key.
        stored_hash: Expected SHA-256 hash from DB.

    Returns:
        True if hashes match, False otherwise.
    """
    calculated_hash = hash_api_key(raw_key)
    return secrets.compare_digest(calculated_hash, stored_hash)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token.

    Args:
        data: Payload dictionary to encode.
        expires_delta: Token lifespan. Defaults to 24 hours.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=24)

    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Args:
        token: JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        AuthenticationException: If token is expired, malformed, or invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise AuthenticationException(f"Invalid or expired JWT token: {str(exc)}")
