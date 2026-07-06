"""Test configuration and shared fixtures.

The suite is hermetic: it runs against an in-memory SQLite database, the
deterministic stub LLM (no network), and no Redis (the cache degrades to a
miss). So `uv run pytest` works on any machine and in CI with zero services.

The same tests can run against Postgres for full-fidelity CI by exporting
TEST_DATABASE_URL (e.g. a postgresql+psycopg://... URL).

Environment must be configured *before* any app module is imported, because a
few modules read settings at import time — so this happens at the very top,
ahead of the app imports below.
"""

import base64
import os

# --- configure settings before importing the app ---------------------------- #
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")
os.environ["SUMMARY_ENCRYPTION_KEY"] = base64.b64encode(b"0" * 32).decode()
os.environ["SUMMARY_ENCRYPTION_KEY_VERSION"] = "1"
os.environ["JWT_SECRET"] = "test-secret-key-32-bytes-minimum-length!"
os.environ["LLM_STUB_MODE"] = "true"
# A cache miss here (no Redis) is fine — the app degrades gracefully.
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402  (imports all models -> registers tables)

_USE_SQLITE = not os.environ.get("TEST_DATABASE_URL")


@pytest_asyncio.fixture
async def engine():
    """A fresh database per test. In-memory SQLite (single shared connection via
    StaticPool) by default; a real engine when TEST_DATABASE_URL is set."""
    if _USE_SQLITE:
        eng = create_async_engine(
            "sqlite+aiosqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    else:
        eng = create_async_engine(os.environ["TEST_DATABASE_URL"])

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(sessionmaker):
    """A session for building fixtures / driving services directly."""
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def client(sessionmaker):
    """An HTTP client wired to the app, with get_db overridden to the test DB.
    Shares the same engine as `db`, so data committed via `db` is visible here."""

    async def _override_get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def auth_headers(accountant) -> dict[str, str]:
    """Bearer header for an accountant ORM object — mints a real JWT the same way
    the login endpoint does."""
    token = create_access_token(
        subject=str(accountant.id),
        role=accountant.role.value,
        firm_id=str(accountant.firm_id) if accountant.firm_id else None,
    )
    return {"Authorization": f"Bearer {token}"}
