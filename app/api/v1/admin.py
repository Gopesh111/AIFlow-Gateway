"""Administrative endpoints for key provisioning, user registration, and quota management."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.db.session import get_db
from app.db.models import User, ApiKey, Quota
from app.services.redis_client import get_redis
from app.schemas.admin import (
    UserCreate,
    UserResponse,
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyListItem,
    QuotaResponse,
    QuotaUpdate,
)
from app.core.security import generate_api_key
from app.core.exceptions import ResourceNotFoundException
from app.api.deps import validate_admin_key

router = APIRouter(prefix="/admin", dependencies=[Depends(validate_admin_key)])


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user account with default monthly token quota."""
    user = User(email=payload.email, is_active=payload.is_active)
    db.add(user)
    await db.flush()

    # Assign default 1M token monthly quota
    now = datetime.now(timezone.utc)
    next_month = now + timedelta(days=30)
    quota = Quota(
        user_id=user.id,
        monthly_token_limit=1000000,
        current_tokens_consumed=0,
        reset_at=next_month,
    )
    db.add(quota)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
) -> List[UserResponse]:
    """List registered users."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def provision_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyResponse:
    """Provision a new API key.

    Returns the unmasked plaintext key in raw_key. This will not be shown again.
    """
    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == payload.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise ResourceNotFoundException(f"User with ID '{payload.user_id}' does not exist.")

    raw_key, hashed_key, prefix = generate_api_key()

    expires_at = None
    if payload.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    api_key = ApiKey(
        user_id=payload.user_id,
        hashed_key=hashed_key,
        key_prefix=prefix,
        name=payload.name,
        rate_limit_rpm=payload.rate_limit_rpm,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyResponse(
        id=api_key.id,
        user_id=api_key.user_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        raw_key=raw_key,
        rate_limit_rpm=api_key.rate_limit_rpm,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.get("/keys", response_model=List[ApiKeyListItem])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
) -> List[ApiKeyListItem]:
    """List all API keys with masked credentials."""
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    keys = result.scalars().all()
    return [ApiKeyListItem.model_validate(k) for k in keys]


@router.delete("/keys/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Revoke an active API key and invalidate its Redis auth cache."""
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise ResourceNotFoundException(f"API Key with ID '{key_id}' not found.")

    api_key.is_revoked = True
    await db.commit()

    # Invalidate Redis auth cache immediately
    redis_cache_key = f"auth:key:{api_key.hashed_key}"
    await redis.delete(redis_cache_key)

    return {"status": "success", "message": f"API key '{key_id}' has been revoked."}
