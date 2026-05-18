"""
AI Calling Agent — Async Database Session
Uses asyncpg + SQLAlchemy async for non-blocking DB operations.
"""
import structlog
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

from app.core.config import settings

log = structlog.get_logger()


def _prepare_database_url(url: str) -> tuple[str, dict]:
    """Normalize URL for asyncpg and extract SSL connect_args."""
    connect_args: dict = {}
    if "sslmode=require" in url:
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")
        connect_args["ssl"] = True
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url, connect_args


class Base(DeclarativeBase):
    pass


engine = None
AsyncSessionLocal = None


def _tables_to_create(sync_conn) -> list:
    """Create only missing CRM tables; skip leads if another app owns that table."""
    from app.models.call import Agent, Call, CallTurn, Lead

    insp = inspect(sync_conn)
    pending = []

    if not insp.has_table("agents"):
        pending.append(Agent.__table__)
    if not insp.has_table("calls"):
        pending.append(Call.__table__)
    if not insp.has_table("call_turns"):
        pending.append(CallTurn.__table__)
    if not insp.has_table("leads"):
        pending.append(Lead.__table__)
    elif insp.has_table("leads"):
        log.info(
            "db.leads_table_exists",
            note="Skipping leads DDL (often shared Supabase schema with non-UUID id)",
        )

    return pending


async def init_db():
    """Initialize DB engine and create tables."""
    global engine, AsyncSessionLocal

    if not settings.db_configured:
        log.warning("db.disabled", reason="DATABASE_URL not set or USE_DATABASE=false")
        return

    db_url, connect_args = _prepare_database_url(settings.DATABASE_URL)
    engine = create_async_engine(
        db_url,
        connect_args=connect_args,
        echo=settings.APP_ENV == "development",
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
    )

    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    from app.models import call  # noqa: F401

    try:
        async with engine.begin() as conn:
            def setup(sync_conn):
                tables = _tables_to_create(sync_conn)
                if tables:
                    Base.metadata.create_all(sync_conn, tables=tables)
                    log.info("db.tables_created", tables=[t.name for t in tables])
                else:
                    log.info("db.tables_up_to_date")

            await conn.run_sync(setup)
        log.info("db.initialized")
    except Exception as e:
        log.warning(
            "db.create_tables_skipped",
            error=str(e),
            hint="Use Docker Postgres or run scripts/init_db.sql on a fresh database",
        )


async def close_db():
    if engine:
        await engine.dispose()
        log.info("db.closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB sessions."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized. Set USE_DATABASE=true and DATABASE_URL.")
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
