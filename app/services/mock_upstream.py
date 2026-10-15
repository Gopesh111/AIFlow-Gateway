"""Simulated upstream LLM / microservice provider with realistic token calculation and latency."""

import asyncio
import uuid
from typing import Dict, Any

from app.config import settings
from app.core.logger import get_logger

logger = get_logger("aiflow.upstream")


class MockUpstreamService:
    """Simulates upstream OpenAI/Anthropic LLM API with non-blocking I/O delay."""

    def __init__(self, latency_ms: int = None) -> None:
        self.latency_ms = (
            latency_ms
            if latency_ms is not None
            else settings.UPSTREAM_SIMULATED_LATENCY_MS
        )

    async def execute(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Execute mock completion request with non-blocking sleep.

        Args:
            prompt: Text prompt from client.
            model: Model name.
            max_tokens: Limit on tokens generated.
            temperature: Sampling temperature.

        Returns:
            Dictionary matching LLM completion schema.
        """
        # Non-blocking async sleep simulating remote inference network round-trip
        delay_seconds = max(self.latency_ms / 1000.0, 0.01)
        await asyncio.sleep(delay_seconds)

        # Generate realistic contextual response
        completion_text = (
            f"Processed prompt successfully: '{prompt[:45]}...' "
            f"via upstream model '{model}'. "
            f"The distributed system verified state consistency and returned synthetic inference tokens."
        )

        prompt_tokens = max(len(prompt.split()) + 4, 1)
        completion_tokens = min(max(len(completion_text.split()) + 2, 1), max_tokens)
        total_tokens = prompt_tokens + completion_tokens

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "model": model,
            "content": completion_text,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }
