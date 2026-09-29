"""Fon vazifalari: kechikish nazorati, ish vaqti ochilishi, eslatmalar, FAQ tahlili."""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import timedelta

from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import delete, select

from ..db import session_scope, utcnow
from ..models import Chat, Lead, LoginToken, ReminderLog, ReminderStep
from . import ai, settings, worktime
from .notify import hub, telegram_staff

log = logging.getLogger(__name__)

_tasks: list[asyncio.Task] = []


LOOP_TITLES = {
    "chats": "Chat kechikish nazorati",
    "subs": "Obuna va guruh nazorati",
    "reminders": "Avto-eslatmalar",
    "faq": "Savollar tahlili",
    "cleanup": "Tozalash",
    "payments": "To'lov eslatmalari",
    "promos": "Promokod muddati va limiti nazorati",
    "tgchats": "Guruh va kanal a'zolari hisobi",
    "channel_ai": "Kanal uchun kunlik AI g'oyalar",
    "group_posts": "Guruhlarga rejalashtirilgan postlar",
    "monitor": "Tizim monitoringi",
}
_named: dict[str, asyncio.Task] = {}


async def _loop(name: str, interval: int, fn) -> None:
    from . import health

    await asyncio.sleep(5)
    while True:
        try:
            await fn()
            health.loop_mark(name, True)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("Fon vazifasi xatosi: %s", name)
            health.loop_mark(name, False, str(e))
        await asyncio.sleep(interval)


async def subs_check() -> None:
    from . import subscriptions

    await subscriptions.daily_check()


async def monitor_check() -> None:
    from . import health

    await health.monitor()


# ------------------------------------------------------------------ chat nazorati


async def check_chats() -> None:
    from ..bot.texts import t
    from . import sender

    now = utcnow()
    wait_min = int(await settings.get("sla_wait_minutes") or 10)
    idle_min = int(await settings.get("idle_reply_minutes") or 5)
    working = await worktime.is_working_time()
    async with session_scope() as s:
        waiting = (await s.execute(select(Chat).where(Chat.status == "waiting"))).scalars().all()
        active = (await s.execute(select(Chat).where(Chat.status == "active"))).scalars().all()

    for c in waiting:
        # ish vaqti boshlandi — navbatdagi so'rovlar haqida operatorlarga xabar
        if working and not c.opened_notified:
            async with session_scope() as s:
                obj = await s.get(Chat, c.id)
                obj.opened_notified = True
            await telegram_staff(f"🌅 Ish vaqtidan tashqari kelgan murojaat navbatda: <b>{html.escape(c.lead.display)}</b> 📱 {c.lead.phone or '—'}",
                                 online_operators=True, path=f"/chats/{c.id}")
            await hub.emit("alert", {"level": "info", "text": f"Navbatda murojaat: {c.lead.display}", "chat_id": c.id})
        # 10 daqiqada hech kim olmasa — adminga
        if working and not c.sla_alert_sent and now - c.sla_start >= timedelta(minutes=wait_min):
            async with session_scope() as s:
                obj = await s.get(Chat, c.id)
                obj.sla_alert_sent = True
            mins = int((now - c.sla_start).total_seconds() // 60)
            await telegram_staff(
                f"⚠️ <b>Kechikish!</b> Murojaatni {mins} daqiqadan beri hech kim olmadi.\n👤 {html.escape(c.lead.display)} 📱 {c.lead.phone or '—'}",
                admins=True, online_operators=True, path=f"/chats/{c.id}")
            await hub.emit("alert", {"level": "danger", "text": f"{c.lead.display} {mins} daqiqadan beri kutmoqda!", "chat_id": c.id})
            if await settings.get("sla_notify_lead"):
                await sender.send_text(c.lead.tg_id, t("sla_apology", c.lead.lang))

    for c in active:
        if c.idle_alert_sent or not c.last_lead_msg_at:
            continue
        if c.last_operator_msg_at and c.last_operator_msg_at >= c.last_lead_msg_at:
            continue
        if now - c.last_lead_msg_at >= timedelta(minutes=idle_min):
            async with session_scope() as s:
                obj = await s.get(Chat, c.id)
                obj.idle_alert_sent = True
            mins = int((now - c.last_lead_msg_at).total_seconds() // 60)
            op = c.operator.display_name if c.operator else "?"
            await hub.emit("alert", {"level": "warning", "chat_id": c.id,
                                     "text": f"{c.lead.display} {mins} daqiqadan beri javob kutmoqda ({op})"},
                           staff_ids={c.operator_id} if c.operator_id else None)
            await hub.emit("alert", {"level": "warning", "chat_id": c.id,
                                     "text": f"{op}: {c.lead.display} ga {mins} daqiqa javob berilmadi"}, admins_only=True)
            ids = [c.operator_id] if c.operator_id else []
            await telegram_staff(f"⏰ <b>{html.escape(c.lead.display)}</b> {mins} daqiqadan beri javobingizni kutmoqda!",
                                 staff_ids=ids, path=f"/chats/{c.id}")
            await telegram_staff(f"⏰ Operator <b>{html.escape(op)}</b> faol chatda {mins} daqiqa javob bermadi: {html.escape(c.lead.display)}",
                                 admins=True, path=f"/chats/{c.id}")


# ------------------------------------------------------------------ eslatmalar


async def send_reminders() -> None:
    from . import sender

    if not await settings.get("reminders_enabled"):
        return
    if not await worktime.in_window("reminder_hours_from", "reminder_hours_to"):
        return
    now = utcnow()
    async with session_scope() as s:
        steps = (await s.execute(select(ReminderStep).where(ReminderStep.is_active.is_(True))
                                 .order_by(ReminderStep.day_offset))).scalars().all()
        if not steps:
            return
        max_day = max(x.day_offset for x in steps)
        leads = (await s.execute(select(Lead).where(
            Lead.is_blocked.is_(False), Lead.reminders_stopped.is_(False),
            Lead.status.not_in(("accepted", "rejected")),
            Lead.created_at >= now - timedelta(days=max_day + 3),
        ))).scalars().all()
        sent_pairs = set((await s.execute(select(ReminderLog.lead_id, ReminderLog.step_id))).all())
        # faol chatdagi leadlarni bezovta qilmaymiz
        busy = set((await s.execute(select(Chat.lead_id).where(Chat.status.in_(("waiting", "active"))))).scalars().all())
    count = 0
    for lead in leads:
        if lead.id in busy:
            continue
        age_days = (now - lead.created_at).days
        for step in steps:
            if (lead.id, step.id) in sent_pairs or age_days < step.day_offset:
                continue
            if age_days > step.day_offset + 2:  # eskirgan qadam — o'tkazib yuboramiz
                async with session_scope() as s:
                    s.add(ReminderLog(lead_id=lead.id, step_id=step.id, ok=False))
                continue
            text = step.text_ru if lead.lang == "ru" else step.text_uz
            ok = True
            try:
                if step.material and step.material.file_path:
                    from ..bot.instance import get_bot

                    doc = step.material.tg_file_id or FSInputFile(step.material.file_path, filename=step.material.file_name)
                    await get_bot().send_document(lead.tg_id, doc, caption=text[:1024])
                else:
                    ok = (await sender.send_text(lead.tg_id, text)) is not None
            except TelegramForbiddenError:
                ok = False
                async with session_scope() as s:
                    obj = await s.get(Lead, lead.id)
                    obj.is_blocked = True
            except Exception as e:  # noqa: BLE001
                log.warning("Eslatma xatosi: %s", e)
                ok = False
            async with session_scope() as s:
                s.add(ReminderLog(lead_id=lead.id, step_id=step.id, ok=ok))
            if ok:
                from .chats import add_message

                await add_message(lead.id, "bot", text=f"[Eslatma, {step.day_offset}-kun] {text}", emit=False)
            count += 1
            await asyncio.sleep(0.1)
            break  # bir leadga bir vaqtda bitta eslatma
    if count:
        log.info("Eslatmalar yuborildi: %s", count)


# ------------------------------------------------------------------ FAQ


async def auto_faq() -> None:
    if not await settings.get("faq_auto_enabled"):
        return
    now = worktime.now_local()
    if now.hour != int(await settings.get("faq_auto_hour") or 3):
        return
    last = await settings.get("faq_last_run")
    if last and str(last)[:10] == now.date().isoformat():
        return
    if not await ai.is_available():
        return
    res = await ai.analyze_questions()
    log.info("FAQ avto tahlil: %s", res)
    if res.get("created"):
        await telegram_staff(f"💡 FAQ tahlili: {res['created']} ta yangi taklif tasdiqlashingizni kutmoqda.",
                             admins=True, path="/faq")


# ------------------------------------------------------------------ yarim qolgan to'lov


async def pay_reminders() -> None:
    """To'lov oynasi ochilib, to'lanmay qolgan buyurtmalarga bir marta eslatma."""
    from ..bot.keyboards import ib
    from ..bot.texts import money, t
    from ..models import Payment
    from . import payme, sender
    from .chats import add_message
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from . import promo as promo_svc

    # promokodi endi amal qilmaydigan (limit tugagan, muddati o'tgan, o'chirilgan) to'lanmagan buyurtmalar — bekor
    await promo_svc.sweep()
    if not await settings.get("pay_reminder_enabled"):
        return
    minutes = max(5, int(await settings.get("pay_reminder_minutes") or 60))
    now = utcnow()
    async with session_scope() as s:
        rows = (await s.execute(select(Payment).where(
            Payment.state.in_((0, 1)), Payment.reminded.is_(False), Payment.amount > 0,
            Payment.created_at <= now - timedelta(minutes=minutes),
            Payment.created_at >= now - timedelta(hours=12),
        ).order_by(Payment.created_at))).scalars().all()
        paid_after = {}
        for p in rows:
            later = (await s.execute(select(Payment.id).where(
                Payment.tg_id == p.tg_id, Payment.id != p.id,
                (Payment.id > p.id) | ((Payment.state == 2) & (Payment.paid_at >= p.created_at))))).first()
            paid_after[p.id] = bool(later)
            obj = await s.get(Payment, p.id)
            obj.reminded = True  # har holda bir marta
        leads = {p.id: (await s.get(Lead, p.lead_id)) if p.lead_id else None for p in rows}
    seen: set[int] = set()
    for p in rows:
        # keyinroq yangi buyurtma yaratgan yoki to'lagan bo'lsa — eslatmaymiz; bir odamga bitta eslatma
        if paid_after.get(p.id) or p.tg_id in seen:
            continue
        seen.add(p.tg_id)
        if p.promo_id and await promo_svc.validate_order(p):
            continue  # promokod joyini boshqalar egallagan — to'lashga undamaymiz
        lead = leads.get(p.id)
        if lead and lead.is_blocked:
            continue
        lang = lead.lang if lead else "uz"
        try:
            url = await payme.checkout_url(p, lang)
        except Exception as e:  # noqa: BLE001
            log.warning("Checkout URL xatosi: %s", e)
            continue
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("pay_btn", lang), url=url)],
            [ib(t("operator_btn_inline", lang), "cta:operator")],
        ])
        text = t("pay_reminder", lang, title=html.escape(p.title), amount=money(p.amount, lang))
        ok = (await sender.send_text(p.tg_id, text, reply_markup=kb)) is not None
        if ok and lead:
            await add_message(lead.id, "bot", text=f"[To'lov eslatmasi] {p.title} — {money(p.amount)}", emit=False)
        await asyncio.sleep(0.1)


async def promo_check() -> None:
    from . import promo as promo_svc

    await promo_svc.sweep()


async def tgchats_job() -> None:
    from . import tgchats

    await tgchats.bootstrap()
    await tgchats.snapshot_all()


async def channel_ai_job() -> None:
    from . import channel

    await channel.daily_job()


async def group_posts_job() -> None:
    from . import group_posts

    await group_posts.due_job()


async def cleanup() -> None:
    from ..models import LoginCode

    async with session_scope() as s:
        await s.execute(delete(LoginToken).where(LoginToken.created_at < utcnow() - timedelta(hours=1)))
        await s.execute(delete(LoginCode).where(LoginCode.created_at < utcnow() - timedelta(hours=1)))


SPECS = {
    "chats": (30, check_chats),
    "subs": (900, subs_check),
    "reminders": (300, send_reminders),
    "faq": (600, auto_faq),
    "cleanup": (3600, cleanup),
    "payments": (300, pay_reminders),
    "promos": (60, promo_check),
    "tgchats": (3600, tgchats_job),
    "channel_ai": (600, channel_ai_job),
    "group_posts": (30, group_posts_job),
    "monitor": (300, monitor_check),
}


def start_all(only: list[str] | None = None) -> None:
    for name, (interval, fn) in SPECS.items():
        if only and name not in only:
            continue
        task = asyncio.create_task(_loop(name, interval, fn))
        _named[name] = task
        _tasks.append(task)


def dead_loops() -> list[str]:
    return [n for n in SPECS if n not in _named or _named[n].done()]


async def restart(keep_monitor: bool = False) -> None:
    """Fon vazifalarini qayta ishga tushirish (monitor o'zini o'zi to'xtatmasligi uchun keep_monitor)."""
    names = [n for n in SPECS if not (keep_monitor and n == "monitor")]
    for n in names:
        t = _named.get(n)
        if t and not t.done():
            t.cancel()
    start_all(only=names)


async def stop_all() -> None:
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    _tasks.clear()
    _named.clear()
