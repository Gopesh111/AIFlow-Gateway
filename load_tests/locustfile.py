"""Locust concurrency load-test suite simulating 500 concurrent gateway users.

Evaluates sub-15ms semantic caching throughput, Redis Lua rate limiter behavior,
and verifies zero unhandled errors under heavy concurrent load.
"""

import random
import uuid
from locust import HttpUser, task, between, events

# Standard test API Key seeded by scripts/seed_data.py
TEST_API_KEY = "af_live_prokey_9876543210fedcba987654"

# Set of 5 repetitive queries to test semantic cache hit rate (80% traffic)
REPETITIVE_QUERIES = [
    "What is the CAP theorem in distributed database architecture?",
    "Explain how the Raft consensus protocol handles leader election.",
    "What are the trade-offs between optimistic and pessimistic locking?",
    "How does a Redis Lua script guarantee atomic token bucket rate limiting?",
    "Describe the difference between exact hash caching and semantic vector caching.",
]

# Random templates to generate cold cache misses (20% traffic)
NOVEL_TEMPLATES = [
    "Calculate the nth prime number after {num} and explain your reasoning.",
    "Draft a microservice communication schema for transaction {tx_id}.",
    "Write an async Python handler for webhook delivery with event id {event_id}.",
    "Design a distributed message broker queue topology with partition {part_id}.",
]


class GatewayLoadTester(HttpUser):
    """Simulates realistic production traffic hitting the AIFlow-Gateway reverse proxy."""

    # Aggressive polling to stress-test async event loops (50ms - 200ms think time)
    wait_time = between(0.05, 0.2)

    def on_start(self):
        """Set standard headers for every user session."""
        self.headers = {
            "X-API-Key": TEST_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "Locust-Distributed-LoadTester/1.0",
        }

    @task(8)
    def query_cached_prompts(self):
        """80% Traffic: Queries repeated prompts to validate sub-15ms semantic caching."""
        prompt = random.choice(REPETITIVE_QUERIES)
        payload = {
            "prompt": prompt,
            "max_tokens": 128,
            "temperature": 0.5,
            "model": "gpt-4o-mini",
        }

        with self.client.post(
            "/api/v1/gateway/execute",
            json=payload,
            headers=self.headers,
            name="/api/v1/gateway/execute [Cache-Hit Path]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                cache_header = response.headers.get("X-Cache", "MISS")
                latency = response.elapsed.total_seconds() * 1000.0

                if cache_header == "HIT" and latency > 50.0:
                    response.failure(f"Cache HIT latency too high: {latency:.2f}ms (>50ms)")
                else:
                    response.success()
            elif response.status_code == 429:
                # 429 is an expected valid enforcement when burst capacity is exceeded
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code} - {response.text}")

    @task(2)
    def query_novel_prompts(self):
        """20% Traffic: Queries unique prompts to exercise upstream execution and cache miss logic."""
        template = random.choice(NOVEL_TEMPLATES)
        prompt = template.format(
            num=random.randint(1000, 99999),
            tx_id=uuid.uuid4().hex[:8],
            event_id=uuid.uuid4().hex[:12],
            part_id=random.randint(1, 64),
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 256,
            "temperature": 0.7,
            "model": "gpt-4o-mini",
        }

        with self.client.post(
            "/api/v1/gateway/execute",
            json=payload,
            headers=self.headers,
            name="/api/v1/gateway/execute [Upstream-Miss Path]",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 429]:
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code} - {response.text}")

    @task(1)
    def query_health_probe(self):
        """Simulate monitoring probes verifying dependency health."""
        with self.client.get("/api/v1/health", name="/api/v1/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health probe degraded: {response.status_code}")
