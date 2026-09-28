"""Bot harakatlari: operatorga ulanish, tarifga yozilish so'rovi, obuna sotib olish."""
from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from ..db import session_scope
from ..models import Lead, Payment, SubscriptionPlan, Tariff
from ..services import chats as chat_svc
from ..services import payme, worktime
from .common import send_menu, update_lead
from .instance import get_bot
from .keyboards import contact_kb, ib
from .texts import money, t


async def require_phone(lead: Lead, pending: str | None = None, ref: int | None = None) -> bool:
    """Telefon yo'q bo'lsa so'raydi. True — telefon bor."""
    if lead.phone:
        return True
    if pending:
        await update_lead(lead.id, pending_input=pending, pending_ref=ref)
    await get_bot().send_message(lead.tg_id, t("phone_required", lead.lang), reply_markup=contact_kb(lead.lang))
    return False


async def operator_request(lead: Lead, reason: str = "user", note: str | None = None, silent_ok: bool = False) -> None:
    bot = get_bot()
    async with session_scope() as s:
        existing = await chat_svc.active_chat(s, lead.id)
        op_name = existing.operator.display_name if existing and existing.operator else None
        existing_status = existing.status if existing else None
    if existing_status == "waiting":
        if note:
            await chat_svc.add_message(lead.id, "system", chat_id=existing.id, text=f"Qo'shimcha so'rov: {note}")
        if not silent_ok:
            await bot.send_message(lead.tg_id, t("already_waiting", lead.lang))
        return
    if existing_status == "active":
        if note:
            await chat_svc.add_message(lead.id, "system", chat_id=existing.id, text=f"Qo'shimcha so'rov: {note}")
        await bot.send_message(lead.tg_id, t("already_active", lead.lang, operator=html.escape(op_name or "")))
        return
    chat, created, off_hours = await chat_svc.request_operator(lead.id, reason=reason, note=note)
    if silent_ok:
        return
    if off_hours:
        nxt = await worktime.next_opening()
        text = t("operator_off_hours", lead.lang, hours=await worktime.work_hours_text(),
                 next_open=nxt.strftime("%d.%m.%Y %H:%M"))
    else:
        text = t("operator_wait", lead.lang)
    await bot.send_message(lead.tg_id, text)


async def enroll_request(lead: Lead, tariff_id: int) -> None:
    """2–4-tariflar: to'lov admin orqali — operator navbatiga so'rov."""
    async with session_scope() as s:
        tr = await s.get(Tariff, tariff_id)
    if not tr:
        return
    lead = await update_lead(lead.id, interested_tariff=tr.name_uz, status="trial" if lead.status in ("new", "contacted", "thinking") else lead.status)
    await get_bot().send_message(lead.tg_id, t("enroll_request_ok", lead.lang))
    await operator_request(lead, reason="enroll", note=f"Tarifga yozilmoqchi: {tr.name_uz}", silent_ok=True)


async def plans_kb(lang: str) -> tuple[str | None, InlineKeyboardMarkup | None]:
    async with session_scope() as s:
        tr = (await s.execute(select(Tariff).where(Tariff.is_subscription.is_(True), Tariff.is_active.is_(True))
                              .order_by(Tariff.sort))).scalars().first()
        if not tr:
            return None, None
        plans = (await s.execute(select(SubscriptionPlan).where(SubscriptionPlan.tariff_id == tr.id,
                                                                SubscriptionPlan.is_active.is_(True))
                                 .order_by(SubscriptionPlan.sort, SubscriptionPlan.days))).scalars().all()
    rows = []
    for p in plans:
        title = p.title_ru if lang == "ru" else p.title_uz
        label = f"{title} — {money(p.price, lang)}" if p.price > 0 else f"{title} — {t('price_ask_admin', lang)}"
        rows.append([ib(label, f"plan:{p.id}")])
    rows.append([ib(t("admin_btn_inline", lang), f"enroll:{tr.id}")])
    name = tr.name_ru if lang == "ru" else tr.name_uz
    return name, InlineKeyboardMarkup(inline_keyboard=rows)


async def show_buy(lead: Lead) -> None:
    name, kb = await plans_kb(lead.lang)
    if not name:
        await get_bot().send_message(lead.tg_id, t("buy_unavailable", lead.lang))
        return
    await get_bot().send_message(lead.tg_id, t("buy_title", lead.lang, tariff=html.escape(name)) + "\n\n" + t("price_note", lead.lang),
                                 reply_markup=kb)


async def start_payment(lead: Lead, plan_id: int) -> None:
    bot = get_bot()
    async with session_scope() as s:
        plan = await s.get(SubscriptionPlan, plan_id)
    if not plan or not plan.is_active:
        await show_buy(lead)
        return
    if plan.price <= 0 or not await payme.is_configured():
        await bot.send_message(lead.tg_id, t("buy_unavailable", lead.lang),
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ib(t("admin_btn_inline", lead.lang), f"enroll:{plan.tariff_id}")]]))
        return
    payment, url = await payme.create_order(lead, plan_id)
    title = (plan.tariff.name_ru if lead.lang == "ru" else plan.tariff.name_uz) + " — " + (plan.title_ru if lead.lang == "ru" else plan.title_uz)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("pay_btn", lead.lang), url=url)]])
    await bot.send_message(lead.tg_id, t("invoice", lead.lang, order=payment.id, title=html.escape(title), days=plan.days,
                                         amount=money(plan.price, lead.lang).rsplit(" ", 1)[0]), reply_markup=kb)
    await chat_svc.add_message(lead.id, "system", text=f"💳 To'lov buyurtmasi №{payment.id}: {payment.title}, {payment.amount:,} so'm".replace(",", " "))


async def run_pending_after_phone(lead: Lead) -> bool:
    """Telefon olingandan keyin kutilgan harakatni bajaradi."""
    pending, ref = lead.pending_input, lead.pending_ref
    if not pending or not pending.startswith("after_phone"):
        return False
    lead = await update_lead(lead.id, pending_input=None, pending_ref=None)
    await send_menu(lead.tg_id, lead, t("phone_saved", lead.lang, phone=lead.phone))
    if pending == "after_phone_operator":
        await operator_request(lead)
    return True


async def last_payments(tg_id: int, limit: int = 5) -> list[Payment]:
    async with session_scope() as s:
        return list((await s.execute(select(Payment).where(Payment.tg_id == tg_id, Payment.state.in_((2, -2)))
                                     .order_by(Payment.id.desc()).limit(limit))).scalars().all())
