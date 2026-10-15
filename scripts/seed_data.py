"""Bootstrap initial admin user, test keys, and quotas in PostgreSQL."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from app.db.session import async_session_factory, async_engine
from app.db.models import Base, User, ApiKey, Quota
from app.core.security import hash_api_key

DEFAULT_TEST_KEY_RAW = "af_live_testkey_1234567890abcdef123456"
PRO_TEST_KEY_RAW = "af_live_prokey_9876543210fedcba987654"


async def seed() -> None:
    """Create initial seed users, test API keys, and default quotas."""
    print("🌱 Connecting to database to seed default records...")

    async with async_engine.begin() as conn:
        # Create tables if not existing
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # 1. Check if admin user already exists
        admin_email = "admin@aiflow.internal"
        result = await session.execute(select(User).where(User.email == admin_email))
        user = result.scalar_one_or_none()

        if not user:
            print(f"Creating default user: {admin_email}")
            user = User(
                id=uuid.uuid4(),
                email=admin_email,
                is_active=True,
            )
            session.add(user)
            await session.flush()

            # Create Quota
            quota = Quota(
                user_id=user.id,
                monthly_token_limit=10000000,  # 10M tokens
                current_tokens_consumed=0,
                reset_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            session.add(quota)

        # 2. Seed Standard Test Key (60 RPM)
        test_hash = hash_api_key(DEFAULT_TEST_KEY_RAW)
        key_result = await session.execute(select(ApiKey).where(ApiKey.hashed_key == test_hash))
        if not key_result.scalar_one_or_none():
            test_key = ApiKey(
                user_id=user.id,
                hashed_key=test_hash,
                key_prefix=DEFAULT_TEST_KEY_RAW[:12],
                name="Default Free Test Key (60 RPM)",
                rate_limit_rpm=60,
                is_revoked=False,
            )
            session.add(test_key)
            print(f"Provisioned Free Key: {DEFAULT_TEST_KEY_RAW}")

        # 3. Seed Pro Test Key (600 RPM)
        pro_hash = hash_api_key(PRO_TEST_KEY_RAW)
        pro_result = await session.execute(select(ApiKey).where(ApiKey.hashed_key == pro_hash))
        if not pro_result.scalar_one_or_none():
            pro_key = ApiKey(
                user_id=user.id,
                hashed_key=pro_hash,
                key_prefix=PRO_TEST_KEY_RAW[:12],
                name="Pro High-Throughput Test Key (600 RPM)",
                rate_limit_rpm=600,
                is_revoked=False,
            )
            session.add(pro_key)
            print(f"Provisioned Pro Key: {PRO_TEST_KEY_RAW}")

        await session.commit()

    await async_engine.dispose()
    print("Database seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
