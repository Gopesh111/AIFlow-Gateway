"""SQLAlchemy 2.0 async declarative database models."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    String,
    Boolean,
    Integer,
    BigInteger,
    Float,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for all application models."""
    pass


class User(Base):
    """User account entity owning API keys and billing quotas."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    api_keys: Mapped[List["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    quota: Mapped[Optional["Quota"]] = relationship(
        "Quota",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


class ApiKey(Base):
    """Client API key credentials with distinct rate limits and revocation state."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hashed_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    key_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    rate_limit_rpm: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")
    request_logs: Mapped[List["RequestLog"]] = relationship(
        "RequestLog",
        back_populates="api_key",
        lazy="noload",
    )


class RequestLog(Base):
    """Audit log entry capturing request latency, status, tokens, and cache telemetry."""

    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    cache_hit: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    tokens_used: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    api_key: Mapped[Optional["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="request_logs",
    )


class Quota(Base):
    """Monthly token consumption and budget allotment per user."""

    __tablename__ = "quotas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    monthly_token_limit: Mapped[int] = mapped_column(
        BigInteger,
        default=1000000,
        nullable=False,
    )
    current_tokens_consumed: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="quota")
