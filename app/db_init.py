"""VYRO — quick dev DB bootstrap (no Alembic needed):
    python -m app.db_init
Creates all tables + trigram indexes. For production use Alembic migrations.
"""
from __future__ import annotations

import asyncio

from alembic import command
from alembic.config import Config


async def create_all() -> None:
    from app.core.database import Base, engine
    from app import models  # noqa: F401  (register metadata)
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_posts_content_trgm ON posts USING gin (content gin_trgm_ops)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_profiles_username_trgm ON user_profiles USING gin (username gin_trgm_ops)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_profiles_display_name_trgm ON user_profiles USING gin (display_name gin_trgm_ops)"
        ))
    await engine.dispose()
    print("[VYRO] all tables + trigram indexes created")


if __name__ == "__main__":
    asyncio.run(create_all())
