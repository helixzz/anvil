from __future__ import annotations

import os

os.environ.setdefault("ANVIL_BEARER_TOKEN", "test-bearer-token-xxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault("ANVIL_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANVIL_RUNNER_SOCKET", "/tmp/nonexistent-anvil-runner.sock")

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from anvil import db as anvil_db
from anvil.config import get_settings


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    """Per-test FastAPI app bound to a fresh in-memory aiosqlite engine.

    Each test gets its own engine (single-connection StaticPool so
    `:memory:` survives across sessions) and schema freshly created
    from the SQLAlchemy metadata. The module-level `anvil.db` engine
    is swapped for this test engine and restored after the test to
    keep tests isolated from each other.
    """
    import anvil.models  # noqa: F401  # ensure metadata is populated
    from anvil.db import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    saved_engine = anvil_db._engine
    saved_maker = anvil_db._sessionmaker
    anvil_db._engine = engine
    anvil_db._sessionmaker = sessionmaker

    get_settings.cache_clear()

    from anvil.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {os.environ['ANVIL_BEARER_TOKEN']}"},
    ) as client:
        yield client

    anvil_db._engine = saved_engine
    anvil_db._sessionmaker = saved_maker
    await engine.dispose()


@pytest.fixture
def admin_token() -> str:
    return os.environ["ANVIL_BEARER_TOKEN"]
