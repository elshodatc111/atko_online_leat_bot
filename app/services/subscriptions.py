"""Premium obuna va yopiq Telegram guruhni boshqarish.

- To'lov (Payme) yoki admin orqali obuna beriladi/uzaytiriladi.
- Guruhga faqat "qo'shilish so'rovi" orqali kiriladi — bot faqat obunasi faol bo'lganlarni tasdiqlaydi.
- Obunasi tugaganlar va to'lovsiz kirganlar avtomatik chiqariladi.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from ..db import session_scope, utcnow
from ..models import Lead, Payment, Staff, Subscription, SubscriptionEvent, Tariff
from . import settings, worktime
from .notify import hub, telegram_staff

log = logging.getLogger(__name__)

EVENT_LABELS = {
    "payme": "💳 Payme to'lovi", "manual": "✍️ Admin qo'lda berdi", "set_date": "📅 Muddat o'zgartirildi",
    "refund": "↩️ To'lov qaytarildi", "revoke": "⛔️ Bekor qilindi", "removed": "🚪 Guruhdan chiqarildi",
    "joined": "✅ Guruhga qo'shildi", "left": "👋 Guruhdan chiqdi", "link": "🔗 Havola yuborildi",
    "denied": "🚫 Kirish rad etildi",
}


# ------------------------------------------------------------------ yordamchilar


async def group_id() -> int | None:
    raw = str(await settings.get("group_chat_id") or "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


async def premium_tariff_name(lang: str = "uz") -> str:
    async with session_scope() as s:
        tr = (await s.execute(select(Tariff).where(Tariff.is_subscription.is_(True)).order_by(Tariff.sort))).scalars().first()
    if not tr:
        return "ATKO Premium"
    return tr.name_ru if lang == "ru" else tr.name_uz


async def get(tg_id: int) -> Subscription | None:
    async with session_scope() as s:
        return (await s.execute(select(Subscription).where(Subscription.tg_id == tg_id))).scalars().first()


async def is_active(tg_id: int) -> bool:
    sub = await get(tg_id)
    return bool(sub and sub.is_active)


async def _staff_ids() -> set[int]:
    async with session_scope() as s:
        return set((await s.execute(select(Staff.tg_id).where(Staff.tg_id.is_not(None), Staff.is_active.is_(True)))).scalars().all())


async def is_allowed(tg_id: int) -> bool:
    return tg_id in await _staff_ids() or await is_active(tg_id)


def fmt_date(dt: datetime | None) -> str:
    return worktime.fmt(dt, "%d.%m.%Y") if dt else "—"


def _join_kb(link: str, lang: str) -> InlineKeyboardMarkup:
    from ..bot.texts import t

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("join_btn", lang), url=link)]])


def renew_kb(lang: str) -> InlineKeyboardMarkup:
    from ..bot.texts import t

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("renew_btn", lang), callback_data="buy")]])


async def _log(sub_id: int, kind: str, *, days: int | None = None, payment_id: int | None = None,
               staff_id: int | None = None, note: str | None = None) -> None:
    async with session_scope() as s:
        s.add(SubscriptionEvent(subscription_id=sub_id, kind=kind, days=days, payment_id=payment_id,
                                staff_id=staff_id, note=note))


async def _lead_by_tg(tg_id: int) -> Lead | None:
    async with session_scope() as s:
        return (await s.execute(select(Lead).where(Lead.tg_id == tg_id))).scalars().first()


# ------------------------------------------------------------------ obuna berish / o'zgartirish


async def extend(tg_id: int, days: int, *, kind: str = "manual", payment_id: int | None = None,
                 staff_id: int | None = None, note: str | None = None, name: str | None = None,
                 whitelisted: bool | None = None) -> Subscription:
    """Obunani berish yoki uzaytirish: yangi muddat = max(hozir, eski muddat) + kunlar."""
    lead = await _lead_by_tg(tg_id)
    now = utcnow()
    async with session_scope() as s:
        sub = (await s.execute(select(Subscription).where(Subscription.tg_id == tg_id))).scalars().first()
        if sub is None:
            sub = Subscription(tg_id=tg_id, started_at=now, expires_at=now)
            s.add(sub)
        base = sub.expires_at if sub.expires_at and sub.expires_at > now else now
        if base == now:
            sub.started_at = now
        sub.expires_at = base + timedelta(days=days)
        sub.reminded_3 = sub.reminded_1 = sub.expired_notified = False
        sub.removed_at = None
        if lead:
            sub.lead_id = lead.id
        sub.name = name or sub.name or (lead.display if lead else None)
        if whitelisted is not None:
            sub.whitelisted = whitelisted
        if note:
            sub.note = note
        await s.flush()
        sid = sub.id
    await _log(sid, kind, days=days, payment_id=payment_id, staff_id=staff_id, note=note)
    if lead and lead.status != "accepted":
        async with session_scope() as s:
            obj = await s.get(Lead, lead.id)
            obj.status = "accepted"
            obj.accepted_at = obj.accepted_at or now
            obj.reminders_stopped = True
    await hub.emit("subscription", {"tg_id": tg_id})
    return await get(tg_id)


async def set_expiry(tg_id: int, expires_local: datetime, staff_id: int | None, whitelisted: bool = False,
                     note: str | None = None) -> Subscription | None:
    exp = worktime.local_to_utc_naive(expires_local)
    async with session_scope() as s:
        sub = (await s.execute(select(Subscription).where(Subscription.tg_id == tg_id))).scalars().first()
        if not sub:
            return None
        sub.expires_at = exp
        sub.whitelisted = whitelisted
        sub.reminded_3 = sub.reminded_1 = sub.expired_notified = False
        if note is not None:
            sub.note = note or None
        sid = sub.id
    await _log(sid, "set_date", staff_id=staff_id, note=f"{expires_local.strftime('%d.%m.%Y')}{' (muddatsiz)' if whitelisted else ''}")
    sub = await get(tg_id)
    if sub and not sub.is_active:
        await remove_from_group(tg_id, notify=True)
    return sub


async def revoke(tg_id: int, staff_id: int | None, note: str | None = None) -> None:
    async with session_scope() as s:
        sub = (await s.execute(select(Subscription).where(Subscription.tg_id == tg_id))).scalars().first()
        if not sub:
            return
        sub.expires_at = utcnow()
        sub.whitelisted = False
        sid = sub.id
    await _log(sid, "revoke", staff_id=staff_id, note=note)
    await remove_from_group(tg_id, notify=False)


async def refund_payment(payment: Payment) -> None:
    """Payme'da to'lov bekor qilinsa — shu to'lov kunlarini ayiramiz, muddat tugasa guruhdan chiqaramiz."""
    from ..bot.texts import t

    async with session_scope() as s:
        sub = (await s.execute(select(Subscription).where(Subscription.tg_id == payment.tg_id))).scalars().first()
        if not sub:
            return
        sub.expires_at = sub.expires_at - timedelta(days=payment.days)
        sid = sub.id
        active = sub.is_active
    await _log(sid, "refund", days=-payment.days, payment_id=payment.id, note=f"{payment.amount} so'm")
    lead = await _lead_by_tg(payment.tg_id)
    lang = lead.lang if lead else "uz"
    from . import sender

    await sender.send_text(payment.tg_id, t("sub_refunded", lang))
    if not active:
        await remove_from_group(payment.tg_id, notify=False)
    await telegram_staff(f"↩️ Payme to'lovi bekor qilindi: №{payment.id}, {payment.amount:,} so'm, {html.escape(payment.title)}".replace(",", " "),
                         admins=True, path="/payments")


# ------------------------------------------------------------------ guruh bilan ishlash


async def invite_link(tg_id: int, force_new: bool = False) -> str | None:
    """Shaxsiy "qo'shilish so'rovi" havolasi (boshqaga berilsa ham, bot faqat obunachini tasdiqlaydi)."""
    from ..bot.instance import get_bot

    gid = await group_id()
    if not gid:
        return None
    sub = await get(tg_id)
    if sub and sub.invite_link and not force_new:
        return sub.invite_link
    link = await get_bot().create_chat_invite_link(gid, name=f"ATKO {tg_id}"[:32], creates_join_request=True)
    async with session_scope() as s:
        obj = (await s.execute(select(Subscription).where(Subscription.tg_id == tg_id))).scalars().first()
        if obj:
            obj.invite_link = link.invite_link
    return link.invite_link


async def send_access(tg_id: int, text_key: str = "paid_ok", staff_id: int | None = None) -> tuple[bool, str | None, str | None]:
    """Obunachiga guruh havolasini yuboradi. Qaytaradi: (yuborildimi, havola, xato)."""
    from ..bot.texts import t
    from . import sender

    sub = await get(tg_id)
    if not sub:
        return False, None, "Obuna topilmadi"
    lead = await _lead_by_tg(tg_id)
    lang = lead.lang if lead else "uz"
    try:
        link = await invite_link(tg_id)
    except Exception as e:  # noqa: BLE001
        return False, None, f"Havola yaratib bo'lmadi (bot guruhda admin emasmi?): {e}"
    if not link:
        return False, None, "Guruh ID si sozlanmagan (Sozlamalar → Yopiq guruh)"
    until = "∞" if sub.whitelisted else fmt_date(sub.expires_at)
    mid = await sender.send_text(tg_id, t(text_key, lang, until=until), reply_markup=_join_kb(link, lang))
    if mid is None:
        return False, link, "Foydalanuvchi botni ishga tushirmagan yoki bloklagan — havolani unga qo'lda yuboring"
    await _log(sub.id, "link", staff_id=staff_id)
    return True, link, None


async def member_status(tg_id: int) -> str | None:
    from ..bot.instance import get_bot

    gid = await group_id()
    if not gid:
        return None
    try:
        m = await get_bot().get_chat_member(gid, tg_id)
        return m.status if isinstance(m.status, str) else m.status.value
    except Exception:  # noqa: BLE001
        return None


async def remove_from_group(tg_id: int, notify: bool = True) -> bool:
    """Guruhdan chiqarish (ban + unban — keyin qayta qo'shila oladi)."""
    from ..bot.instance import get_bot
    from ..bot.texts import t
    from . import sender

    gid = await group_id()
    if not gid:
        return False
    status = await member_status(tg_id)
    if status in ("creator", "administrator"):
        return False
    removed = False
    if status in ("member", "restricted"):
        try:
            bot = get_bot()
            await bot.ban_chat_member(gid, tg_id)
            await bot.unban_chat_member(gid, tg_id, only_if_banned=True)
            removed = True
        except Exception as e:  # noqa: BLE001
            log.warning("Guruhdan chiqarib bo'lmadi %s: %s", tg_id, e)
            return False
    async with session_scope() as s:
        sub = (await s.execute(select(Subscription).where(Subscription.tg_id == tg_id))).scalars().first()
        if sub:
            sub.in_group = False
            if removed:
                sub.removed_at = utcnow()
            sid = sub.id
        else:
            sid = None
    if removed and sid:
        await _log(sid, "removed")
    if removed and notify:
        lead = await _lead_by_tg(tg_id)
        lang = lead.lang if lead else "uz"
        await sender.send_text(tg_id, t("sub_expired", lang), reply_markup=renew_kb(lang))
    return removed


async def handle_join_request(req) -> None:
    from ..bot.texts import t
    from . import sender

    gid = await group_id()
    if not gid or req.chat.id != gid:
        return
    uid = req.from_user.id
    lead = await _lead_by_tg(uid)
    lang = lead.lang if lead else "uz"
    if await is_allowed(uid):
        await req.approve()
        sub = await get(uid)
        if sub:
            await _log(sub.id, "joined")
        await sender.send_text(uid, t("join_approved", lang))
    else:
        await req.decline()
        sub = await get(uid)
        if sub:
            await _log(sub.id, "denied")
        await sender.send_text(uid, t("join_denied", lang), reply_markup=renew_kb(lang))


async def handle_member_update(upd) -> None:
    """Guruhga kim qo'shilsa/chiqsa — nazorat."""
    gid = await group_id()
    if not gid or upd.chat.id != gid:
        return
    user = upd.new_chat_member.user
    if user.is_bot:
        return
    new = upd.new_chat_member.status
    new = new if isinstance(new, str) else new.value
    sub = await get(user.id)
    if new in ("member", "restricted"):
        if sub:
            async with session_scope() as s:
                obj = await s.get(Subscription, sub.id)
                obj.in_group = True
        if await settings.get("group_kick_unpaid") and not await is_allowed(user.id):
            await remove_from_group(user.id, notify=False)
            await telegram_staff(f"🚫 Obunasiz foydalanuvchi guruhdan chiqarildi: {html.escape(user.full_name)} (<code>{user.id}</code>)",
                                 admins=True, path="/subscriptions")
    elif new in ("left", "kicked") and sub:
        async with session_scope() as s:
            obj = await s.get(Subscription, sub.id)
            obj.in_group = False


async def daily_check() -> dict:
    """Eslatmalar (3 va 1 kun oldin) va muddati tugaganlarni chiqarish."""
    from ..bot.texts import t
    from . import sender

    now = utcnow()
    days_list = sorted({int(d) for d in (await settings.get("group_reminder_days") or [3, 1])}, reverse=True)
    async with session_scope() as s:
        subs = (await s.execute(select(Subscription).where(Subscription.whitelisted.is_(False)))).scalars().all()
    reminded = removed = 0
    for sub in subs:
        lead = await _lead_by_tg(sub.tg_id)
        lang = lead.lang if lead else "uz"
        left_sec = (sub.expires_at - now).total_seconds()
        if left_sec > 0:
            d_first, d_last = max(days_list), min(days_list)
            flag = None
            if left_sec <= d_last * 86400 and not sub.reminded_1:
                flag = "reminded_1"
            elif left_sec <= d_first * 86400 and not sub.reminded_3 and not sub.reminded_1:
                flag = "reminded_3"
            if flag:
                await sender.send_text(sub.tg_id, t("sub_remind", lang, days=max(1, sub.days_left), until=fmt_date(sub.expires_at)),
                                       reply_markup=renew_kb(lang))
                async with session_scope() as s:
                    obj = await s.get(Subscription, sub.id)
                    obj.reminded_3 = True
                    if flag == "reminded_1":
                        obj.reminded_1 = True
                reminded += 1
            continue
        if not sub.expired_notified:
            was_removed = await remove_from_group(sub.tg_id, notify=True)
            if not was_removed:
                await sender.send_text(sub.tg_id, t("sub_expired", lang), reply_markup=renew_kb(lang))
            async with session_scope() as s:
                obj = await s.get(Subscription, sub.id)
                obj.expired_notified = True
            removed += 1
        elif sub.in_group:
            await remove_from_group(sub.tg_id, notify=False)
    return {"reminded": reminded, "removed": removed}


async def sync_group() -> dict:
    """Har bir obunachining guruhdagi holatini tekshiradi."""
    async with session_scope() as s:
        subs = (await s.execute(select(Subscription))).scalars().all()
    in_group = 0
    for sub in subs:
        st = await member_status(sub.tg_id)
        flag = st in ("member", "restricted", "administrator", "creator")
        in_group += 1 if flag else 0
        async with session_scope() as s:
            obj = await s.get(Subscription, sub.id)
            obj.in_group = flag
        if flag and not sub.is_active and st in ("member", "restricted"):
            await remove_from_group(sub.tg_id, notify=False)
    return {"total": len(subs), "in_group": in_group}
