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
        if p.closed_reason == "expired" or (p.expires_at and p.expires_at <= utcnow()):
            return p, "promo_expired"
        if not p.is_active:
            return p, "promo_inactive"
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


PROMO_CANCEL_REASON = 100  # ichki sabab kodi: promokod endi amal qilmaydi (Payme kodi emas)


async def validate_order(payment) -> str | None:
    """Promokodli to'lanmagan buyurtma hali ham amal qiladimi. Xato kaliti yoki None."""
    if not payment.promo_id:
        return None
    async with session_scope() as s:
        p = await s.get(PromoCode, payment.promo_id)
        if not p:
            return "promo_not_found"
        if p.closed_reason == "expired" or (p.expires_at and p.expires_at <= utcnow()):
            return "promo_expired"
        if not p.is_active:
            return "promo_inactive"
        if (await s.execute(select(PromoUse.id).where(PromoUse.promo_id == p.id, PromoUse.tg_id == payment.tg_id))).first():
            return "promo_used_by_you"
        if p.max_uses:
            # boshqalar band qilgan joylar: Payme jarayonidagilar (state=1) va oxirgi 30 daqiqadagi yangi buyurtmalar
            others = (await s.execute(select(func.count(Payment.id)).where(
                Payment.promo_id == p.id, Payment.tg_id != payment.tg_id, Payment.id != payment.id,
                (Payment.state == 1) | ((Payment.state == 0) &
                                        (Payment.created_at > utcnow() - timedelta(minutes=RESERVE_MINUTES)))))).scalar_one()
            if p.used_count >= p.max_uses or p.used_count + others >= p.max_uses:
                return "promo_exhausted"
    return None


async def cancel_order(payment_id: int, err_key: str, notify: bool = True) -> bool:
    """To'lanmagan (state=0) promokodli buyurtmani bekor qiladi va foydalanuvchiga xabar beradi."""
    from aiogram.types import InlineKeyboardMarkup

    from ..bot.keyboards import ib
    from ..bot.texts import t
    from ..models import Lead
    from . import sender
    from .chats import add_message
    from .notify import hub

    async with session_scope() as s:
        obj = await s.get(Payment, payment_id)
        if not obj or obj.state != 0:
            return False
        obj.state = -1
        obj.reason = PROMO_CANCEL_REASON
        obj.cancelled_at = utcnow()
        tg_id, promo_id, lead_id = obj.tg_id, obj.promo_id, obj.lead_id
        lead = await s.get(Lead, lead_id) if lead_id else None
        if lead and lead.promo_id == promo_id:
            lead.promo_id = None
        lang = lead.lang if lead else "uz"
        blocked = bool(lead and lead.is_blocked)
    await hub.emit("payment", {"id": payment_id, "state": -1})
    if lead_id:
        await add_message(lead_id, "system", text=f"✖️ Promokodli buyurtma №{payment_id} avtomatik bekor qilindi ({err_key})", emit=False)
    if notify and not blocked:
        kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("buy_btn_inline", lang), "buy")],
                                                   [ib(t("operator_btn_inline", lang), "cta:operator")]])
        await sender.send_text(tg_id, t("promo_order_cancelled", lang, order=payment_id, reason=t(err_key, lang)), reply_markup=kb)
    return True


async def cancel_pending(promo_id: int, err_key: str) -> int:
    """Promokod limiti tugagan / o'chirilgan bo'lsa — shu promokodli barcha to'lanmagan buyurtmalarni bekor qiladi."""
    async with session_scope() as s:
        ids = (await s.execute(select(Payment.id).where(Payment.promo_id == promo_id, Payment.state == 0))).scalars().all()
    n = 0
    for pid in ids:
        if await cancel_order(pid, err_key):
            n += 1
    return n


async def is_exhausted(promo_id: int) -> bool:
    async with session_scope() as s:
        p = await s.get(PromoCode, promo_id)
        return bool(p and p.max_uses and p.used_count >= p.max_uses)


async def expire_due() -> list[str]:
    """Muddati tugagan faol promokodlarni avtomatik o'chiradi va to'lanmagan buyurtmalarini bekor qiladi."""
    import html as _html

    from .notify import hub, telegram_staff

    now = utcnow()
    async with session_scope() as s:
        rows = (await s.execute(select(PromoCode).where(PromoCode.is_active.is_(True), PromoCode.expires_at.is_not(None),
                                                        PromoCode.expires_at <= now))).scalars().all()
        done = []
        for p in rows:
            p.is_active = False
            p.closed_reason = "expired"
            p.closed_at = now
            done.append((p.id, p.code, p.used_count, p.max_uses))
    codes = []
    for pid, code, used, mx in done:
        n = await cancel_pending(pid, "promo_expired")
        codes.append(code)
        await hub.emit("alert", {"level": "info", "text": f"⌛ Promokod {code} muddati tugadi — avtomatik o'chirildi"}, admins_only=True)
        await telegram_staff(f"⌛ Promokod <b>{_html.escape(code)}</b> muddati tugadi va avtomatik o'chirildi.\n"
                             f"Ishlatilgan: {used}/{mx or '∞'}" + (f"\nTo'lanmagan buyurtmalar bekor qilindi: {n} ta" if n else ""),
                             admins=True, path="/promos")
    return codes


async def sweep() -> int:
    """Fon tekshiruvi: limiti tugagan, muddati o'tgan yoki o'chirilgan promokodli to'lanmagan buyurtmalarni bekor qiladi."""
    await expire_due()
    async with session_scope() as s:
        rows = (await s.execute(select(Payment).where(Payment.promo_id.is_not(None), Payment.state == 0))).scalars().all()
    n = 0
    for pay in rows:
        err = await validate_order(pay)
        # boshqalar band qilgan bo'lsa ham (vaqtincha) — bekor qilmaymiz; faqat qat'iy holatlar
        if err in ("promo_not_found", "promo_inactive", "promo_expired", "promo_used_by_you") or \
                (err == "promo_exhausted" and await is_exhausted(pay.promo_id)):
            if await cancel_order(pay.id, err):
                n += 1
    return n
