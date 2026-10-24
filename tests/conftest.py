"""Shared pytest fixtures.

Tests run against a REAL PostgreSQL database (`flowdesk_test`), not SQLite
or mocks - several models use PostgreSQL-only types (JSONB, ARRAY, native
UUID) and the tenant-isolation tests need real query behavior.

Schema is created once per test session via a plain sync connection
(psycopg2, no event loop involved). Each test function then gets its own
async engine bound to its own event loop - sharing one async engine across
pytest-asyncio's per-test event loops is what causes the classic
"attached to a different loop" asyncpg errors, so we deliberately avoid it.
Tables are truncated before every test for isolation.
"""
import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/flowdesk_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("EMAIL_ENABLED", "false")

import pytest
import pytest_asyncio
import sqlalchemy
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

get_settings.cache_clear()
settings = get_settings()


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    """Create the schema once, synchronously, before any test runs."""
    from app import models  # noqa: F401 populate metadata
    from app.database import Base

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    sync_engine = sqlalchemy.create_engine(sync_url)
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    yield
    Base.metadata.drop_all(bind=sync_engine)
    sync_engine.dispose()


@pytest_asyncio.fixture
async def db_engine():
    """A fresh async engine bound to the current test's event loop."""
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(db_engine):
    from app.database import Base

    async with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_engine):
    from app.database import get_db
    from app.main import app

    session_factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"
