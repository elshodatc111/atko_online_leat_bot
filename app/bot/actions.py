"""Bot harakatlari: operatorga ulanish, tarifga yozilish so'rovi, obuna sotib olish."""
from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from ..db import session_scope
from ..models import Lead, Payment, SubscriptionPlan, Tariff
from ..services import chats as chat_svc
from ..services import payme, settings, worktime
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


async def enroll_request(lead: Lead, tariff_id: int | None, option_id: int | None = None) -> None:
    """Zoom / Individual paketini tanlash — menejerlar navbatiga yozilish so'rovi."""
    from ..models import TariffOption
    from ..services import tariffs as tariff_svc

    label = None
    async with session_scope() as s:
        if option_id:
            o = await s.get(TariffOption, option_id)
            if not o or not o.is_active:
                return
            tr = o.tariff
            label = (f"{tr.name_uz} — {tariff_svc.option_title(o)} ({tariff_svc.option_details(o)})"
                     + (f", {tariff_svc.fmt_money(o.price)} so'm" if o.price else ""))
        else:
            tr = await s.get(Tariff, tariff_id)
    if not tr:
        return
    interested = label or tr.name_uz
    lead = await update_lead(lead.id, interested_tariff=interested[:128],
                             status="trial" if lead.status in ("new", "contacted", "thinking") else lead.status)
    await get_bot().send_message(lead.tg_id, t("enroll_request_ok", lead.lang))
    await operator_request(lead, reason="enroll", note=f"Tarifga yozilmoqchi: {interested}", silent_ok=True)


async def _sub_tariff():
    async with session_scope() as s:
        return (await s.execute(select(Tariff).where(Tariff.is_subscription.is_(True), Tariff.is_active.is_(True))
                                .order_by(Tariff.sort))).scalars().first()


async def plans_kb(lead: Lead) -> tuple[str | None, InlineKeyboardMarkup | None]:
    lang = lead.lang
    tr = await _sub_tariff()
    if not tr:
        return None, None
    async with session_scope() as s:
        plans = (await s.execute(select(SubscriptionPlan).where(SubscriptionPlan.tariff_id == tr.id,
                                                                SubscriptionPlan.is_active.is_(True))
                                 .order_by(SubscriptionPlan.sort, SubscriptionPlan.days))).scalars().all()
    rows = []
    for p in plans:
        if p.price <= 0:
            continue  # narxi kiritilmagan variant sotilmaydi
        rows.append([ib(f"{p.title_uz} — {money(p.price, lang)}", f"plan:{p.id}")])
    if await settings.get("sample_video_file_id"):
        rows.append([ib(t("sample_btn", lang), "sample")])
    rows.append([ib(t("operator_btn_inline", lang), "cta:operator")])
    return tr.name_uz, InlineKeyboardMarkup(inline_keyboard=rows)


async def show_buy(lead: Lead) -> None:
    name, kb = await plans_kb(lead)
    if not name:
        await get_bot().send_message(lead.tg_id, t("buy_unavailable", lead.lang))
        return
    text = t("buy_title", lead.lang, tariff=html.escape(name), desc="").replace("\n\n\n\n", "\n\n")
    text += "\n\n" + t("price_note", lead.lang)
    await get_bot().send_message(lead.tg_id, text[:4090], reply_markup=kb)


async def send_sample(lead: Lead) -> bool:
    """Namuna video — Telegram bulutidagi file_id orqali (serverdan qayta yuklanmaydi)."""
    fid = await settings.get("sample_video_file_id")
    if not fid:
        return False
    cap = await settings.get("sample_video_caption_uz") or ""
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("buy_btn_inline", lead.lang), "buy")]])
    await get_bot().send_video(lead.tg_id, fid, caption=html.escape(cap)[:1024], reply_markup=kb)
    return True


async def start_payment(lead: Lead, plan_id: int) -> None:
    bot = get_bot()
    async with session_scope() as s:
        plan = await s.get(SubscriptionPlan, plan_id)
    if not plan or not plan.is_active or not plan.tariff or not plan.tariff.is_subscription or plan.price <= 0:
        await show_buy(lead)
        return
    op_kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("operator_btn_inline", lead.lang), "cta:operator")]])
    if not await payme.is_configured():
        await bot.send_message(lead.tg_id, t("buy_unavailable", lead.lang), reply_markup=op_kb)
        return
    title = f"{plan.tariff.name_uz} — {plan.title_uz}"
    payment, url = await payme.create_order(lead, plan_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("pay_btn", lead.lang), url=url)]])
    await bot.send_message(lead.tg_id, t("invoice", lead.lang, order=payment.id, title=html.escape(title), days=plan.days,
                                         amount=money(payment.amount, lead.lang).rsplit(" ", 1)[0]), reply_markup=kb)
    await chat_svc.add_message(lead.id, "system", text=f"💳 To'lov buyurtmasi №{payment.id}: {payment.title}, {payment.amount:,} so'm".replace(",", " "))


async def run_pending_after_phone(lead: Lead) -> bool:
    """Telefon olingandan keyin kutilgan harakatni bajaradi."""
    pending = lead.pending_input
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
