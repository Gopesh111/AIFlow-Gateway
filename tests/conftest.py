"""Shared Pytest fixtures for AIFlow-Gateway asynchronous tests."""

import time
import uuid
import math
from typing import AsyncGenerator, Dict, Any, Set
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.models import Base, User, ApiKey, Quota
from app.db.session import get_db
from app.services.redis_client import get_redis
from app.core.security import hash_api_key

TEST_API_KEY_RAW = "af_live_conftest_key_1234567890abcdef"
ADMIN_KEY_RAW = "af_master_admin_secret_key_prod_2026"


class MockRedisScript:
    """In-memory emulation of the token-bucket Redis Lua script."""

    def __init__(self, mock_redis: "MockRedis"):
        self.mock_redis = mock_redis

    async def __call__(self, keys, args):
        key = keys[0]
        capacity = float(args[0])
        refill_rate = float(args[1])
        now = float(args[2])
        requested = float(args[3])
        ttl = int(args[4])

        data = self.mock_redis.hashes.get(key, {})
        tokens = data.get("tokens")
        last_refill = data.get("last_refill")

        if tokens is None or last_refill is None:
            tokens = capacity
            last_refill = now
        else:
            delta = max(0.0, now - last_refill)
            tokens = min(capacity, tokens + (delta * refill_rate))
            last_refill = now

        allowed = 0
        retry_after = 0

        if tokens >= requested:
            allowed = 1
            tokens = tokens - requested
        else:
            allowed = 0
            missing = requested - tokens
            retry_after = int(math.ceil(missing / refill_rate))

        self.mock_redis.hashes[key] = {"tokens": tokens, "last_refill": last_refill}
        return [allowed, int(math.floor(tokens)), retry_after]


class MockRedis:
    """In-memory asynchronous mock implementation of Redis."""

    def __init__(self):
        self.store: Dict[str, str] = {}
        self.sets: Dict[str, Set[str]] = {}
        self.hashes: Dict[str, Dict[str, Any]] = {}
        self.ttls: Dict[str, float] = {}

    async def get(self, key: str) -> str:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int = None) -> bool:
        self.store[key] = str(value)
        if ex:
            self.ttls[key] = time.time() + ex
        return True

    async def delete(self, key: str) -> int:
        deleted = 0
        if key in self.store:
            del self.store[key]
            deleted += 1
        if key in self.sets:
            del self.sets[key]
            deleted += 1
        if key in self.hashes:
            del self.hashes[key]
            deleted += 1
        return deleted

    async def smembers(self, key: str) -> Set[str]:
        return self.sets.get(key, set())

    async def sadd(self, key: str, value: str) -> int:
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].add(str(value))
        return 1

    async def srem(self, key: str, value: str) -> int:
        if key in self.sets and str(value) in self.sets[key]:
            self.sets[key].remove(str(value))
            return 1
        return 0

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = time.time() + seconds
        return True

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass

    def register_script(self, script_code: str):
        return MockRedisScript(self)


@pytest.fixture
def mock_redis() -> MockRedis:
    """Provide clean in-memory MockRedis."""
    return MockRedis()


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async database engine for isolated test runs."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_maker() as session:
        # Seed test user
        user = User(
            id=uuid.uuid4(),
            email="tester@aiflow.test",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        # Seed test API key (60 RPM)
        api_key = ApiKey(
            id=uuid.uuid4(),
            user_id=user.id,
            hashed_key=hash_api_key(TEST_API_KEY_RAW),
            key_prefix=TEST_API_KEY_RAW[:12],
            name="Conftest Test Key",
            rate_limit_rpm=60,
            is_revoked=False,
        )
        session.add(api_key)
        await session.commit()

        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def async_client(test_db_session: AsyncSession, mock_redis: MockRedis) -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous HTTP test client with overridden database and redis dependencies."""
    async def override_get_db():
        yield test_db_session

    async def override_get_redis():
        yield mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
