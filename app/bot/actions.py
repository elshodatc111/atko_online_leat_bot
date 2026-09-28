"""Bot harakatlari: operatorga ulanish, tarifga yozilish so'rovi, obuna sotib olish."""
from __future__ import annotations

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from ..db import session_scope
from ..models import Lead, Payment, SubscriptionPlan, Tariff
from ..services import chats as chat_svc
from ..db import utcnow
from ..services import payme, settings, worktime
from ..services import promo as promo_svc
from ..services.notify import telegram_staff
from .common import send_menu, strip_placeholders, update_lead
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


async def _sub_tariff():
    async with session_scope() as s:
        return (await s.execute(select(Tariff).where(Tariff.is_subscription.is_(True), Tariff.is_active.is_(True))
                                .order_by(Tariff.sort))).scalars().first()


async def active_promo(lead: Lead):
    """Leadga qo'llangan va hali amal qiladigan promokod (yo'q bo'lsa None)."""
    if not lead.promo_id:
        return None
    p, err = await promo_svc.check(int(lead.promo_id), lead.tg_id)
    if err:
        await update_lead(lead.id, promo_id=None)
        return None
    return p


async def plans_kb(lead: Lead) -> tuple[str | None, InlineKeyboardMarkup | None, object]:
    lang = lead.lang
    tr = await _sub_tariff()
    if not tr:
        return None, None, None
    async with session_scope() as s:
        plans = (await s.execute(select(SubscriptionPlan).where(SubscriptionPlan.tariff_id == tr.id,
                                                                SubscriptionPlan.is_active.is_(True))
                                 .order_by(SubscriptionPlan.sort, SubscriptionPlan.days))).scalars().all()
    promo = await active_promo(lead)
    rows = []
    for p in plans:
        title = p.title_ru if lang == "ru" else p.title_uz
        if p.price <= 0:
            label = f"{title} — {t('price_ask_admin', lang)}"
        elif promo and (not promo.plan_id or promo.plan_id == p.id):
            final, _ = promo_svc.apply(p.price, promo.percent)
            label = f"{title} — {money(final, lang)} (−{promo.percent}%)" if final else f"{title} — 🎁 0 {t('som', lang)} (−100%)"
        else:
            label = f"{title} — {money(p.price, lang)}"
        rows.append([ib(label, f"plan:{p.id}")])
    rows.append([ib(t("promo_remove_btn", lang), "promo_off")] if promo else [ib(t("promo_btn", lang), "promo")])
    if await settings.get("sample_video_file_id"):
        rows.append([ib(t("sample_btn", lang), "sample")])
    rows.append([ib(t("admin_btn_inline", lang), f"enroll:{tr.id}")])
    name = tr.name_ru if lang == "ru" else tr.name_uz
    return name, InlineKeyboardMarkup(inline_keyboard=rows), promo


async def show_buy(lead: Lead) -> None:
    lost = None
    if lead.promo_id:
        _, lost = await promo_svc.check(int(lead.promo_id), lead.tg_id)
    name, kb, promo = await plans_kb(lead)
    if not name:
        await get_bot().send_message(lead.tg_id, t("buy_unavailable", lead.lang))
        return
    if lost:
        # qo'llangan promokod endi amal qilmaydi (limit tugadi, muddati o'tdi...) — foydalanuvchiga aytamiz
        await get_bot().send_message(lead.tg_id, t(lost, lead.lang))
    text = t("buy_title", lead.lang, tariff=html.escape(name), desc="").replace("\n\n\n\n", "\n\n")
    if promo:
        text += "\n\n" + t("promo_applied_line", lead.lang, code=promo.code, percent=promo.percent)
    text += "\n\n" + t("price_note", lead.lang)
    await get_bot().send_message(lead.tg_id, text[:4090], reply_markup=kb)


async def send_sample(lead: Lead) -> bool:
    """Namuna video — Telegram bulutidagi file_id orqali (serverdan qayta yuklanmaydi)."""
    fid = await settings.get("sample_video_file_id")
    if not fid:
        return False
    cap = await settings.get("sample_video_caption_ru" if lead.lang == "ru" else "sample_video_caption_uz") or ""
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("buy_btn_inline", lead.lang), "buy")]])
    await get_bot().send_video(lead.tg_id, fid, caption=html.escape(cap)[:1024], reply_markup=kb)
    return True


async def apply_promo_code(lead: Lead, code: str) -> bool:
    p, err = await promo_svc.check(code, lead.tg_id)
    bot = get_bot()
    if err:
        await bot.send_message(lead.tg_id, t(err, lead.lang),
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ib(t("promo_btn", lead.lang), "promo")],
                                                                                  [ib(t("back", lead.lang), "buy")]]))
        return False
    lead = await update_lead(lead.id, promo_id=p.id, pending_input=None)
    await bot.send_message(lead.tg_id, t("promo_ok", lead.lang, code=p.code, percent=p.percent))
    await chat_svc.add_message(lead.id, "system", text=f"🎟 Promokod qo'llandi: {p.code} (−{p.percent}%)")
    await show_buy(lead)
    return True


async def start_payment(lead: Lead, plan_id: int) -> None:
    from ..services import subscriptions

    bot = get_bot()
    async with session_scope() as s:
        plan = await s.get(SubscriptionPlan, plan_id)
    if not plan or not plan.is_active:
        await show_buy(lead)
        return
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("admin_btn_inline", lead.lang), f"enroll:{plan.tariff_id}")]])
    if plan.price <= 0:
        await bot.send_message(lead.tg_id, t("buy_unavailable", lead.lang), reply_markup=admin_kb)
        return
    if lead.promo_id:
        _, lost = await promo_svc.check(int(lead.promo_id), lead.tg_id)
        if lost:
            # promokod qo'llangan edi, lekin endi amal qilmaydi — to'liq narxda jimgina buyurtma yaratmaymiz
            lead = await update_lead(lead.id, promo_id=None)
            await bot.send_message(lead.tg_id, t("promo_lost", lead.lang, reason=t(lost, lead.lang)))
            await show_buy(lead)
            return
    promo = await active_promo(lead)
    if promo and promo.plan_id and promo.plan_id != plan.id:
        await bot.send_message(lead.tg_id, t("promo_wrong_plan", lead.lang))
        promo = None
    amount, discount = promo_svc.apply(plan.price, promo.percent) if promo else (plan.price, 0)
    title = (plan.tariff.name_ru if lead.lang == "ru" else plan.tariff.name_uz) + " — " + (plan.title_ru if lead.lang == "ru" else plan.title_uz)

    if promo and amount == 0:
        # 100% chegirma — Payme'siz darhol faollashtiriladi
        async with session_scope() as s:
            pay = Payment(lead_id=lead.id, tg_id=lead.tg_id, plan_id=plan.id, title=f"{plan.tariff.name_uz} — {plan.title_uz}",
                          days=plan.days, amount=0, original_amount=plan.price, promo_id=promo.id, state=2,
                          paid_at=utcnow(), perform_time=int(utcnow().timestamp() * 1000))
            s.add(pay)
            await s.flush()
            pid = pay.id
        await promo_svc.mark_used(promo.id, lead.tg_id, pid, 0, discount)
        await update_lead(lead.id, promo_id=None)
        if await promo_svc.is_exhausted(promo.id):
            await promo_svc.cancel_pending(promo.id, "promo_exhausted")
        await subscriptions.extend(lead.tg_id, plan.days, kind="manual", payment_id=pid, note=f"Promokod {promo.code} (100%)")
        await subscriptions.send_access(lead.tg_id, "free_ok")
        await chat_svc.add_message(lead.id, "system", text=f"🎁 100% promokod ({promo.code}) bilan obuna faollashtirildi: {plan.days} kun")
        await telegram_staff(f"🎁 Promokod <b>{html.escape(promo.code)}</b> (100%) bilan obuna berildi: {html.escape(lead.display)}, {plan.days} kun",
                             admins=True, path="/subscriptions")
        return

    if not await payme.is_configured():
        await bot.send_message(lead.tg_id, t("buy_unavailable", lead.lang), reply_markup=admin_kb)
        return
    payment, url = await payme.create_order(lead, plan_id, amount=amount, promo_id=promo.id if promo else None,
                                            original_amount=plan.price if promo else None)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("pay_btn", lead.lang), url=url)]])
    extra = f"\n🎟 {promo.code}: −{promo.percent}% (−{money(discount, lead.lang)})" if promo else ""
    await bot.send_message(lead.tg_id, t("invoice", lead.lang, order=payment.id, title=html.escape(title), days=plan.days,
                                         amount=money(amount, lead.lang).rsplit(" ", 1)[0]) + extra, reply_markup=kb)
    note = f" (promokod {promo.code}, −{promo.percent}%)" if promo else ""
    await chat_svc.add_message(lead.id, "system", text=f"💳 To'lov buyurtmasi №{payment.id}: {payment.title}, {payment.amount:,} so'm{note}".replace(",", " "))


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
