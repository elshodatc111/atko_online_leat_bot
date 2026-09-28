"""Promokodlar: foizli chegirma (1–100%), foydalanish soni, muddat va variant bo'yicha cheklov.

Qoidalar:
- Har bir foydalanuvchi bitta promokoddan faqat bir marta foydalanadi.
- Foydalanish to'lov muvaffaqiyatli bo'lganda (yoki 100% chegirmada darhol) hisoblanadi.
- "Birinchi N ta" cheklovida to'lov jarayonidagi buyurtmalar ham vaqtincha band qiladi (30 daqiqa),
  shunda bir vaqtda ko'p odam limitdan oshib ketmaydi.
"""
from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import func, select

from ..db import session_scope, utcnow
from ..models import Payment, PromoCode, PromoUse

RESERVE_MINUTES = 30


def normalize(code: str) -> str:
    return re.sub(r"[^A-Z0-9_\-]", "", (code or "").strip().upper())[:32]


def apply(amount: int, percent: int) -> tuple[int, int]:
    """(yakuniy summa, chegirma)"""
    percent = max(0, min(100, int(percent or 0)))
    discount = amount * percent // 100
    return amount - discount, discount


async def _pending(s, promo_id: int, exclude_tg: int | None = None) -> int:
    q = select(func.count(Payment.id)).where(
        Payment.promo_id == promo_id, Payment.state.in_((0, 1)),
        Payment.created_at > utcnow() - timedelta(minutes=RESERVE_MINUTES))
    if exclude_tg:
        q = q.where(Payment.tg_id != exclude_tg)
    return (await s.execute(q)).scalar_one()


async def check(promo_id_or_code: int | str, tg_id: int, plan_id: int | None = None) -> tuple[PromoCode | None, str | None]:
    """Promokodni tekshiradi. Qaytaradi (promo, xato_kaliti)."""
    async with session_scope() as s:
        if isinstance(promo_id_or_code, int):
            p = await s.get(PromoCode, promo_id_or_code)
        else:
            p = (await s.execute(select(PromoCode).where(PromoCode.code == normalize(promo_id_or_code)))).scalars().first()
        if not p:
            return None, "promo_not_found"
        if not p.is_active:
            return p, "promo_inactive"
        if p.expires_at and p.expires_at < utcnow():
            return p, "promo_expired"
        used = (await s.execute(select(PromoUse.id).where(PromoUse.promo_id == p.id, PromoUse.tg_id == tg_id))).first()
        if used:
            return p, "promo_used_by_you"
        if p.max_uses and p.used_count + await _pending(s, p.id, exclude_tg=tg_id) >= p.max_uses:
            return p, "promo_exhausted"
        if plan_id and p.plan_id and p.plan_id != plan_id:
            return p, "promo_wrong_plan"
    return p, None


async def mark_used(promo_id: int, tg_id: int, payment_id: int | None, amount: int, discount: int) -> None:
    async with session_scope() as s:
        exists = (await s.execute(select(PromoUse.id).where(PromoUse.promo_id == promo_id, PromoUse.tg_id == tg_id))).first()
        if exists:
            return
        s.add(PromoUse(promo_id=promo_id, tg_id=tg_id, payment_id=payment_id, amount=amount, discount=discount))
        p = await s.get(PromoCode, promo_id)
        if p:
            p.used_count = (p.used_count or 0) + 1
