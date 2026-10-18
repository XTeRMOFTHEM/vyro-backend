"""VYRO — Async SQLAlchemy engine / session / DeclarativeBase."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _create_engine():
    kwargs: dict = {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "echo": settings.DB_ECHO,
    }
    return create_async_engine(settings.DATABASE_URL, **kwargs)


engine = _create_engine()
SessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


@event.listens_for(engine.sync_engine, "connect")
def _set_pg_pragmas(dbapi_conn, _record):
    """Connection-level tuning for speed & safety."""
    cur = dbapi_conn.cursor()
    try:
        cur.execute(f"SET statement_timeout = {settings.DB_STATEMENT_TIMEOUT_MS}")
        cur.execute("SET idle_in_transaction_session_timeout = '60s'")
    except Exception:  # pragma: no cover
        pass
    finally:
        cur.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — one session per request, always closed."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
