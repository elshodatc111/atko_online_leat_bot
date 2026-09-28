"""Ish vaqti, dam olish va bayram kunlari (Toshkent vaqti)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from ..config import config
from ..db import session_scope
from ..models import Holiday
from . import settings

TZ = config.TIMEZONE
WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

_holidays_cache: set[date] | None = None


def now_local() -> datetime:
    return datetime.now(TZ)


def to_local(dt: datetime | None) -> datetime | None:
    """Bazadagi UTC (naive) vaqtni Toshkent vaqtiga o'tkazadi."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def local_to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def fmt(dt: datetime | None, pattern: str = "%d.%m.%Y %H:%M") -> str:
    d = to_local(dt)
    return d.strftime(pattern) if d else "—"


def _parse_hm(s: str) -> time:
    h, m = (s or "00:00").split(":")[:2]
    return time(int(h), int(m))


async def reload_holidays() -> set[date]:
    global _holidays_cache
    async with session_scope() as s:
        rows = (await s.execute(select(Holiday.day))).scalars().all()
    _holidays_cache = set(rows)
    return _holidays_cache


async def holidays() -> set[date]:
    if _holidays_cache is None:
        return await reload_holidays()
    return _holidays_cache


async def is_day_off(d: date) -> bool:
    days_off = await settings.get("days_off") or []
    return d.weekday() in days_off or d in await holidays()


async def is_working_time(at: datetime | None = None) -> bool:
    at = at or now_local()
    if await is_day_off(at.date()):
        return False
    start = _parse_hm(await settings.get("work_start"))
    end = _parse_hm(await settings.get("work_end"))
    return start <= at.time() < end


async def next_opening(at: datetime | None = None) -> datetime:
    """Keyingi ish vaqti boshlanishi (lokal vaqt)."""
    at = at or now_local()
    start = _parse_hm(await settings.get("work_start"))
    end = _parse_hm(await settings.get("work_end"))
    d = at.date()
    for i in range(0, 30):
        day = d + timedelta(days=i)
        if await is_day_off(day):
            continue
        opening = datetime.combine(day, start, tzinfo=TZ)
        closing = datetime.combine(day, end, tzinfo=TZ)
        if i == 0 and at >= closing:
            continue
        return max(opening, at) if i == 0 else opening
    return at


async def work_hours_text() -> str:
    return f"{await settings.get('work_start')}–{await settings.get('work_end')}"


async def in_window(from_key: str, to_key: str) -> bool:
    t = now_local().time()
    return _parse_hm(await settings.get(from_key)) <= t < _parse_hm(await settings.get(to_key))
