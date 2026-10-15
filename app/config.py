"""Application configuration management using Pydantic Settings."""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Global configuration settings for AIFlow-Gateway."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    PROJECT_NAME: str = "AIFlow-Gateway"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # PostgreSQL Database
    POSTGRES_USER: str = "aiflow"
    POSTGRES_PASSWORD: str = "aiflow_secret"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "aiflow_db"
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://aiflow:aiflow_secret@localhost:5432/aiflow_db"
    )

    # Database Pool Tuning
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Redis Cache & Distributed Rate Limiter
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 50

    # Security & Master Admin Key
    JWT_SECRET_KEY: str = "super-secret-jwt-signing-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ADMIN_API_KEY: str = "af_master_admin_secret_key_prod_2026"

    # Semantic Caching
    SEMANTIC_CACHE_ENABLED: bool = True
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD: float = 0.92
    SEMANTIC_CACHE_TTL_SECONDS: int = 3600
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Distributed Rate Limiting Defaults
    DEFAULT_RATE_LIMIT_RPM: int = 60
    RATE_LIMIT_BURST_MULTIPLIER: float = 1.2

    # Upstream Mock Configuration
    UPSTREAM_TIMEOUT_SECONDS: float = 10.0
    UPSTREAM_SIMULATED_LATENCY_MS: int = 250


settings = Settings()
