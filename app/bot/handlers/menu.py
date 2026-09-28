"""Asosiy menyu bo'limlari va inline tugmalar."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.types import Message as TgMessage
from sqlalchemy import select

from ...db import session_scope
from ...models import Chat, InfoPage, SubscriptionPlan, Tariff
from ...services import ai, settings, subscriptions, worktime
from ...services.knowledge import CATEGORY_LABELS
from ...services.notify import hub, telegram_staff
from ..actions import enroll_request, last_payments, operator_request, require_phone, send_sample, show_buy, start_payment
from ..common import esc, get_lead, get_or_create_lead, send_menu, strip_placeholders, update_lead
from ..keyboards import cta_kb, ib, lang_kb, quiz_level_kb, skip_comment_kb
from ..texts import all_button_texts, money, t

router = Router(name="menu")

CAT_RU = {"group": "Групповые тарифы", "individual": "Индивидуальные тарифы (1-на-1)", "hybrid": "Гибридное обучение",
          "subscription": "Подписка"}


async def _lead(event) -> object:
    lead = await get_lead(event.from_user.id)
    if lead is None:
        lead, _ = await get_or_create_lead(event.from_user)
    return lead


# ------------------------------------------------------------------ tariflar va narxlar


async def _courses_kb(lang: str) -> InlineKeyboardMarkup:
    async with session_scope() as s:
        items = (await s.execute(select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort, Tariff.id))).scalars().all()
    return InlineKeyboardMarkup(inline_keyboard=[[ib(x.name_ru if lang == "ru" else x.name_uz, f"tariff:{x.id}")] for x in items])


@router.message(F.text.in_(all_button_texts("btn_courses")))
async def courses(msg: TgMessage) -> None:
    lead = await _lead(msg)
    await msg.answer(t("courses_title", lead.lang), reply_markup=await _courses_kb(lead.lang))


@router.callback_query(F.data == "courses")
async def courses_cb(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    await cb.message.edit_text(t("courses_title", lead.lang), reply_markup=await _courses_kb(lead.lang))
    await cb.answer()


async def tariff_price_text(tr: Tariff, lang: str) -> str:
    if tr.is_subscription:
        async with session_scope() as s:
            plans = (await s.execute(select(SubscriptionPlan).where(SubscriptionPlan.tariff_id == tr.id, SubscriptionPlan.is_active.is_(True))
                                     .order_by(SubscriptionPlan.sort, SubscriptionPlan.days))).scalars().all()
        if not plans:
            return f"{t('price_label', lang)}: {t('price_ask_admin', lang)}"
        lines = [f"{t('price_label', lang)}:"]
        for p in plans:
            title = p.title_ru if lang == "ru" else p.title_uz
            lines.append(f"• {esc(title)} — <b>{money(p.price, lang)}</b>" if p.price > 0 else f"• {esc(title)} — {t('price_ask_admin', lang)}")
        return "\n".join(lines)
    if tr.price > 0:
        period = f" / {esc(tr.price_period)}" if tr.price_period else ""
        return f"{t('price_label', lang)}: <b>{money(tr.price, lang)}</b>{period}"
    return f"{t('price_label', lang)}: {t('price_ask_admin', lang)}"


@router.callback_query(F.data.startswith("tariff:"))
async def tariff_detail(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    async with session_scope() as s:
        x = await s.get(Tariff, int(cb.data.split(":")[1]))
    if not x:
        await cb.answer()
        return
    name = x.name_ru if lead.lang == "ru" else x.name_uz
    desc = x.desc_ru if lead.lang == "ru" else x.desc_uz
    await update_lead(lead.id, interested_tariff=x.name_uz)
    rows = []
    if x.is_subscription:
        rows.append([ib(t("buy_btn_inline", lead.lang), "buy")])
    rows.append([ib(t("admin_btn_inline", lead.lang), f"enroll:{x.id}")])
    rows.append([ib(t("back", lead.lang), "courses")])
    text = (f"<b>{esc(name)}</b>\n\n{esc(strip_placeholders(desc))}\n\n{await tariff_price_text(x, lead.lang)}\n\n"
            f"{t('price_note', lead.lang)}")
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("enroll:"))
async def enroll(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    await cb.answer()
    await enroll_request(lead, int(cb.data.split(":")[1]))


# ------------------------------------------------------------------ obuna sotib olish


@router.message(F.text.in_(all_button_texts("btn_buy")))
async def buy(msg: TgMessage) -> None:
    await show_buy(await _lead(msg))


@router.callback_query(F.data == "buy")
async def buy_cb(cb: CallbackQuery) -> None:
    await cb.answer()
    lead = await _lead(cb)
    if lead.pending_input == "promo":
        lead = await update_lead(lead.id, pending_input=None)
    await show_buy(lead)


@router.callback_query(F.data == "promo")
async def promo_cb(cb: CallbackQuery) -> None:
    await cb.answer()
    lead = await _lead(cb)
    await update_lead(lead.id, pending_input="promo")
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("back", lead.lang), "buy")]])
    await cb.message.answer(t("promo_ask", lead.lang), reply_markup=kb)


@router.callback_query(F.data == "promo_off")
async def promo_off(cb: CallbackQuery) -> None:
    await cb.answer(t("promo_removed", "uz"))
    lead = await update_lead((await _lead(cb)).id, promo_id=None, pending_input=None)
    await show_buy(lead)


@router.callback_query(F.data == "sample")
async def sample_cb(cb: CallbackQuery) -> None:
    await cb.answer()
    await send_sample(await _lead(cb))


@router.callback_query(F.data.startswith("plan:"))
async def plan_cb(cb: CallbackQuery) -> None:
    await cb.answer()
    await start_payment(await _lead(cb), int(cb.data.split(":")[1]))


# ------------------------------------------------------------------ mening obunam


def _bar(days_left: int, total_days: int) -> str:
    total_days = max(total_days, 1)
    filled = max(0, min(10, round(days_left / total_days * 10)))
    return "🟩" * filled + "⬜️" * (10 - filled)


async def mysub_text(lead) -> tuple[str, InlineKeyboardMarkup]:
    sub = await subscriptions.get(lead.tg_id)
    tariff = html.escape(await subscriptions.premium_tariff_name(lead.lang))
    limit = int(await settings.get("tutor_trial_daily") or 0)
    rows = []
    if sub and sub.whitelisted:
        text = t("mysub_forever", lead.lang, tariff=tariff)
        rows.append([ib(t("mysub_link_btn", lead.lang), "sublink")])
    elif sub and sub.is_active:
        total = max(1, int((sub.expires_at - sub.started_at).total_seconds() // 86400))
        text = t("mysub_active", lead.lang, tariff=tariff, start=subscriptions.fmt_date(sub.started_at),
                 until=subscriptions.fmt_date(sub.expires_at), left=sub.days_left, bar=_bar(sub.days_left, total))
        rows.append([ib(t("mysub_link_btn", lead.lang), "sublink")])
        rows.append([ib(t("renew_btn", lead.lang), "buy")])
    elif sub:
        text = t("mysub_expired", lead.lang, tariff=tariff, until=subscriptions.fmt_date(sub.expires_at), limit=limit)
        rows.append([ib(t("renew_btn", lead.lang), "buy")])
    else:
        text = t("mysub_none", lead.lang, limit=limit)
        rows.append([ib(t("btn_buy", lead.lang), "buy")])
    pays = await last_payments(lead.tg_id)
    if pays:
        items = "\n".join(
            f"{'✅' if p.state == 2 else '↩️'} {worktime.fmt(p.paid_at or p.created_at, '%d.%m.%Y')} — {money(p.amount, lead.lang)} ({p.days} kun)"
            for p in pays)
        text += t("mysub_payments", lead.lang, items=items)
    rows.append([ib(t("operator_btn_inline", lead.lang), "cta:operator")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.in_(all_button_texts("btn_mysub")))
async def mysub(msg: TgMessage) -> None:
    lead = await _lead(msg)
    text, kb = await mysub_text(lead)
    await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data == "sublink")
async def sublink(cb: CallbackQuery) -> None:
    await cb.answer()
    lead = await _lead(cb)
    if not await subscriptions.is_active(lead.tg_id):
        await show_buy(lead)
        return
    ok, link, err = await subscriptions.send_access(lead.tg_id, "access_granted")
    if not ok and not link:
        await cb.message.answer(t("buy_unavailable", lead.lang))


# ------------------------------------------------------------------ markaz haqida


@router.message(F.text.in_(all_button_texts("btn_info")))
async def info(msg: TgMessage) -> None:
    lead = await _lead(msg)
    async with session_scope() as s:
        pages = (await s.execute(select(InfoPage).where(InfoPage.show_in_menu.is_(True)).order_by(InfoPage.sort))).scalars().all()
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(p.title_ru if lead.lang == "ru" else p.title_uz, f"info:{p.id}")] for p in pages])
    await msg.answer(t("info_title", lead.lang), reply_markup=kb)


@router.callback_query(F.data.startswith("info:"))
async def info_detail(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    async with session_scope() as s:
        p = await s.get(InfoPage, int(cb.data.split(":")[1]))
    if not p:
        await cb.answer()
        return
    title, body = (p.title_ru, p.body_ru) if lead.lang == "ru" else (p.title_uz, p.body_uz)
    body = strip_placeholders(body) or ("Подробности уточнит менеджер." if lead.lang == "ru" else "Batafsil ma'lumotni menejerimiz beradi.")
    await cb.message.answer(f"<b>{esc(title)}</b>\n\n{esc(body)}", reply_markup=cta_kb(lead.lang))
    await cb.answer()


# ------------------------------------------------------------------ til / operator


@router.message(F.text.in_(all_button_texts("btn_lang")))
async def change_lang(msg: TgMessage) -> None:
    await msg.answer(t("choose_lang", "uz"), reply_markup=lang_kb())


@router.message(F.text.in_(all_button_texts("btn_operator")))
async def operator(msg: TgMessage) -> None:
    lead = await _lead(msg)
    if await require_phone(lead, "after_phone_operator"):
        await operator_request(lead)


@router.callback_query(F.data.startswith("cta:"))
async def cta(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    await cb.answer()
    if cb.data.split(":")[1] == "operator" and await require_phone(lead, "after_phone_operator"):
        await operator_request(lead)


# ------------------------------------------------------------------ AI mentor


async def tutor_state(lead) -> tuple[bool, int, int]:
    """(cheksizmi, bugun qolgan savollar, kunlik limit)"""
    limit = int(await settings.get("tutor_trial_daily") or 0)
    if await subscriptions.is_active(lead.tg_id):
        return True, 10**6, limit
    today = worktime.now_local().date()
    used = lead.tutor_count if lead.tutor_day == today else 0
    return False, max(0, limit - used), limit


async def tutor_allowed(lead) -> bool:
    unlimited, left, _ = await tutor_state(lead)
    return unlimited or left > 0


async def tutor_consume(lead) -> None:
    today = worktime.now_local().date()
    count = lead.tutor_count if lead.tutor_day == today else 0
    await update_lead(lead.id, tutor_day=today, tutor_count=count + 1)


@router.message(F.text.in_(all_button_texts("btn_tutor")))
async def tutor_on(msg: TgMessage) -> None:
    lead = await _lead(msg)
    if not await settings.get("tutor_enabled"):
        await msg.answer(t("tutor_disabled", lead.lang))
        return
    if not await require_phone(lead):
        return
    lead = await update_lead(lead.id, mode="tutor")
    unlimited, left, limit = await tutor_state(lead)
    info = t("tutor_unlimited", lead.lang) if unlimited else t("tutor_daily", lead.lang, left=left, limit=limit)
    await send_menu(msg.chat.id, lead, t("tutor_intro", lead.lang, limit_info=info))


@router.message(F.text.in_(all_button_texts("btn_consultant")))
async def consultant_on(msg: TgMessage) -> None:
    lead = await _lead(msg)
    lead = await update_lead(lead.id, mode="consultant", quiz_state=None)
    await send_menu(msg.chat.id, lead, t("consultant_on", lead.lang))


@router.message(F.text.in_(all_button_texts("btn_quiz")))
async def quiz_start(msg: TgMessage) -> None:
    lead = await _lead(msg)
    await msg.answer(t("quiz_choose_level", lead.lang), reply_markup=quiz_level_kb(lead.lang))


async def _send_quiz(cb: CallbackQuery, lead, level: str, state: dict | None) -> None:
    if not await tutor_allowed(lead):
        await cb.message.answer(t("tutor_limit", lead.lang, limit=await settings.get("tutor_trial_daily")), reply_markup=cta_kb(lead.lang, operator=False))
        return
    if not await ai.is_available():
        await cb.message.answer(t("ai_unavailable", lead.lang))
        return
    wait = await cb.message.answer(t("quiz_wait", lead.lang))
    await cb.bot.send_chat_action(cb.from_user.id, ChatAction.TYPING)
    state = state or {"level": level, "ok": 0, "total": 0, "asked": []}
    try:
        q = await ai.quiz_question(level, lead.lang, state.get("asked"))
    except Exception:  # noqa: BLE001
        q = None
    try:
        await wait.delete()
    except Exception:  # noqa: BLE001
        pass
    if not q:
        await cb.message.answer(t("ai_unavailable", lead.lang))
        return
    await tutor_consume(lead)
    state.update({"level": level, "q": q["question"], "options": q["options"], "correct": q["correct"],
                  "explanation": q["explanation"]})
    state["asked"] = (state.get("asked") or [])[-15:] + [q["question"][:120]]
    await update_lead(lead.id, quiz_state=state)
    letters = "ABCD"
    text = f"📝 <b>{state['total'] + 1}-savol</b>\n\n{esc(q['question'])}\n\n" + "\n".join(
        f"<b>{letters[i]})</b> {esc(o)}" for i, o in enumerate(q["options"]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(letters[i], f"quiz:ans:{i}") for i in range(len(q["options"]))]])
    await cb.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("quiz:lvl:"))
async def quiz_level(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    await cb.answer()
    await _send_quiz(cb, lead, cb.data.split(":")[2], None)


@router.callback_query(F.data.startswith("quiz:ans:"))
async def quiz_answer(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    st = dict(lead.quiz_state or {})
    if "correct" not in st:
        await cb.answer()
        return
    idx = int(cb.data.split(":")[2])
    ok = idx == st["correct"]
    st["total"] = st.get("total", 0) + 1
    st["ok"] = st.get("ok", 0) + (1 if ok else 0)
    answer = f"{'ABCD'[st['correct']]}) {st['options'][st['correct']]}"
    res = t("quiz_correct", lead.lang) if ok else t("quiz_wrong", lead.lang, answer=esc(answer))
    st.pop("correct", None)
    await update_lead(lead.id, quiz_state=st)
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("quiz_next", lead.lang), "quiz:next"), ib(t("quiz_stop", lead.lang), "quiz:stop")]])
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await cb.message.answer(f"{res}\n\n📌 {esc(st.get('explanation', ''))}\n\n{t('quiz_result', lead.lang, ok=st['ok'], total=st['total'])}", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.in_({"quiz:next", "quiz:stop"}))
async def quiz_next(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    st = dict(lead.quiz_state or {})
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    if cb.data == "quiz:stop" or not st:
        await update_lead(lead.id, quiz_state=None)
        await cb.message.answer("🏁 " + t("quiz_result", lead.lang, ok=st.get("ok", 0), total=st.get("total", 0)))
        return
    await _send_quiz(cb, lead, st.get("level", "beginner"), st)


# ------------------------------------------------------------------ baho


@router.callback_query(F.data.startswith("rate:"))
async def rate(cb: CallbackQuery) -> None:
    _, chat_id, val = cb.data.split(":")
    chat_id, val = int(chat_id), int(val)
    lead = await _lead(cb)
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        if not chat or chat.lead_id != lead.id or chat.rating:
            await cb.answer("✔️")
            return
        chat.rating = val
        op_name = chat.operator.display_name if chat.operator else "—"
    await update_lead(lead.id, pending_input="rating_comment", pending_ref=chat_id)
    await cb.message.edit_text(f"{t('rating_ask', lead.lang)} {'⭐' * val}")
    await cb.message.answer(t("rating_comment_ask", lead.lang), reply_markup=skip_comment_kb(chat_id, lead.lang))
    await cb.answer()
    await hub.emit("chat_rated", {"chat_id": chat_id, "rating": val})
    if val <= 2:
        await telegram_staff(f"⚠️ <b>Past baho: {'⭐' * val}</b>\nOperator: {html.escape(op_name)}\nLead: {html.escape(lead.display)}",
                             admins=True, path=f"/chats/{chat_id}")


@router.callback_query(F.data.startswith("rate_skip:"))
async def rate_skip(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    await update_lead(lead.id, pending_input=None, pending_ref=None)
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await send_menu(cb.from_user.id, lead, t("rating_thanks", lead.lang))
    await cb.answer()
