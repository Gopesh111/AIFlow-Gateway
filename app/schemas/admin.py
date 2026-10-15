"""Pydantic schemas for administrative provisioning and key management."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, ConfigDict


class UserCreate(BaseModel):
    """Schema for registering a new user."""

    email: EmailStr = Field(..., description="Unique email address.")
    is_active: bool = Field(default=True, description="Account active state.")


class UserResponse(BaseModel):
    """Public user response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class ApiKeyCreate(BaseModel):
    """Schema for generating a new client API key."""

    user_id: uuid.UUID = Field(..., description="ID of the user owning this key.")
    name: str = Field(..., min_length=2, max_length=100, description="Descriptive label for the key.")
    rate_limit_rpm: int = Field(default=60, ge=1, le=10000, description="Requests per minute quota.")
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="Optional expiration window in days.",
    )


class ApiKeyResponse(BaseModel):
    """Returned only upon key creation. Exposes the raw plaintext key once."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    key_prefix: str
    raw_key: str = Field(..., description="Plaintext key. Will never be shown again.")
    rate_limit_rpm: int
    created_at: datetime
    expires_at: Optional[datetime]


class ApiKeyListItem(BaseModel):
    """List item for keys with masked sensitive credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    key_prefix: str
    rate_limit_rpm: int
    is_revoked: bool
    created_at: datetime
    expires_at: Optional[datetime]


class QuotaResponse(BaseModel):
    """User quota consumption telemetry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    monthly_token_limit: int
    current_tokens_consumed: int
    reset_at: datetime
    updated_at: datetime


class QuotaUpdate(BaseModel):
    """Update user quota allowance."""

    monthly_token_limit: int = Field(..., ge=1000, description="New monthly token ceiling.")
