"""Ma'lumotlar bazasi ulanishi (SQLite + SQLAlchemy async)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import config


def utcnow() -> datetime:
    """Bazada vaqt UTC da (tzinfo'siz) saqlanadi."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(config.db_url(), echo=False, connect_args={"timeout": 30})


if engine.url.get_backend_name() == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with SessionLocal() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


async def init_db() -> None:
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(sync_conn) -> None:
    """Yangi versiyada qo'shilgan ustunlarni mavjud bazaga avtomatik qo'shadi (ma'lumotlar saqlanadi)."""
    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            col_type = col.type.compile(dialect=sync_conn.dialect)
            default_sql = ""
            default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
            if isinstance(default, bool):
                default_sql = f" DEFAULT {1 if default else 0}"
            elif isinstance(default, (int, float)):
                default_sql = f" DEFAULT {default}"
            elif isinstance(default, str):
                default_sql = " DEFAULT '" + default.replace("'", "''") + "'"
            sync_conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}{default_sql}')
