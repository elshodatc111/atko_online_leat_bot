"""Kurs tariflari paketlari (12 dars / 20 dars): nomlash, bir dars narxi, eng tejamkor paket."""
from __future__ import annotations

from sqlalchemy import select

from ..db import session_scope
from ..models import TariffOption


def fmt_money(amount: int) -> str:
    return f"{int(amount or 0):,}".replace(",", " ")


def option_title(o: TariffOption, lang: str = "uz") -> str:
    """«12 dars»"""
    return f"{o.lessons} dars"


def option_details(o: TariffOption, lang: str = "uz") -> str:
    """«haftasiga 3 ta · 1 oy»"""
    return f"haftasiga {o.per_week} ta · {o.months} oy" if o.per_week else f"{o.months} oy"


def per_lesson(o: TariffOption) -> int:
    return round(o.price / o.lessons) if o.price and o.lessons else 0


def best_value(options: list[TariffOption]) -> tuple[int | None, int]:
    """Bir dars narxi eng arzon paket id si va boshqalariga nisbatan tejash foizi."""
    priced = [o for o in options if o.price > 0 and o.lessons > 0]
    if len(priced) < 2:
        return None, 0
    best = min(priced, key=per_lesson)
    worst = max(priced, key=per_lesson)
    if per_lesson(best) >= per_lesson(worst):
        return None, 0
    return best.id, round((1 - per_lesson(best) / per_lesson(worst)) * 100)


async def options_for(tariff_id: int, active_only: bool = True) -> list[TariffOption]:
    async with session_scope() as s:
        q = select(TariffOption).where(TariffOption.tariff_id == tariff_id)
        if active_only:
            q = q.where(TariffOption.is_active.is_(True))
        return list((await s.execute(q.order_by(TariffOption.sort, TariffOption.lessons))).scalars().all())


async def all_options(active_only: bool = True) -> list[TariffOption]:
    async with session_scope() as s:
        q = select(TariffOption)
        if active_only:
            q = q.where(TariffOption.is_active.is_(True))
        return list((await s.execute(q.order_by(TariffOption.tariff_id, TariffOption.sort, TariffOption.lessons))).scalars().all())
