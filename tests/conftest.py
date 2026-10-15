import os
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_for_tests")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_tests")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "999999")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.db import Base, get_session

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s


@pytest_asyncio.fixture
async def client(engine):
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with async_session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def concurrent_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def concurrent_client(concurrent_engine):
    async_session_factory = async_sessionmaker(concurrent_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with async_session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
