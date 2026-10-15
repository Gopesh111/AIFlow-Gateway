"""Pydantic schemas for the reverse proxy gateway endpoint."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class CacheStatus(str, Enum):
    """Cache evaluation result status."""
    HIT = "HIT"
    MISS = "MISS"


class ProxyRequest(BaseModel):
    """Payload submitted to the proxy gateway."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Text prompt to forward to the upstream LLM service.",
        examples=["Explain the Raft consensus algorithm in three bullet points."],
    )
    max_tokens: int = Field(
        default=256,
        ge=1,
        le=4096,
        description="Maximum tokens to generate.",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature.",
    )
    model: str = Field(
        default="gpt-4o-mini",
        description="Target model identifier.",
    )


class TokenUsage(BaseModel):
    """Token consumption breakdown."""

    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)


class ProxyResponse(BaseModel):
    """Structured response returned by the gateway."""

    id: str = Field(..., description="Unique completion identifier.")
    model: str = Field(..., description="Model that produced the completion.")
    content: str = Field(..., description="Generated completion text.")
    usage: TokenUsage = Field(..., description="Token usage details.")
    cached: bool = Field(..., description="Whether response was served from cache.")
    cache_type: Optional[str] = Field(
        None,
        description="Type of cache hit: 'exact' or 'semantic'. None on cache miss.",
    )
    latency_ms: float = Field(..., description="End-to-end execution latency in milliseconds.")
