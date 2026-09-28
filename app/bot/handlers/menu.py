"""Asosiy menyu bo'limlari va inline tugmalar."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.types import Message as TgMessage
from sqlalchemy import select

from ...db import session_scope
from ...models import Chat, Faq, InfoPage, Material, Tariff
from ...services import ai, settings
from ...services.knowledge import CATEGORY_LABELS
from ...services.notify import hub, telegram_staff
from ..actions import operator_request, require_phone, send_material, trial_request
from ..common import esc, get_lead, get_or_create_lead, send_menu, strip_placeholders, update_lead
from ..keyboards import cta_kb, ib, lang_kb, quiz_level_kb, skip_comment_kb
from ..texts import all_button_texts, t

router = Router(name="menu")

CAT_RU = {"group": "Групповые тарифы", "individual": "Индивидуальные тарифы (1-на-1)", "hybrid": "Гибридное обучение"}


async def _lead(event) -> object:
    lead = await get_lead(event.from_user.id)
    if lead is None:
        lead, _ = await get_or_create_lead(event.from_user)
    return lead


# ------------------------------------------------------------------ kurslar


async def _courses_kb(lang: str) -> InlineKeyboardMarkup:
    async with session_scope() as s:
        items = (await s.execute(select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort, Tariff.id))).scalars().all()
    rows = []
    for cat in ("group", "individual", "hybrid"):
        for x in items:
            if x.category == cat:
                rows.append([ib(x.name_ru if lang == "ru" else x.name_uz, f"tariff:{x.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.in_(all_button_texts("btn_courses")))
async def courses(msg: TgMessage) -> None:
    lead = await _lead(msg)
    await msg.answer(t("courses_title", lead.lang), reply_markup=await _courses_kb(lead.lang))


@router.callback_query(F.data == "courses")
async def courses_cb(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    await cb.message.edit_text(t("courses_title", lead.lang), reply_markup=await _courses_kb(lead.lang))
    await cb.answer()


@router.callback_query(F.data.startswith("tariff:"))
async def tariff_detail(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    tid = int(cb.data.split(":")[1])
    async with session_scope() as s:
        x = await s.get(Tariff, tid)
    if not x:
        await cb.answer()
        return
    name = x.name_ru if lead.lang == "ru" else x.name_uz
    desc = x.desc_ru if lead.lang == "ru" else x.desc_uz
    cat = CAT_RU[x.category] if lead.lang == "ru" else CATEGORY_LABELS.get(x.category, "")
    await update_lead(lead.id, interested_tariff=x.name_uz)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [ib(t("trial_btn_inline", lead.lang), "cta:trial")],
        [ib(t("operator_btn_inline", lead.lang), "cta:operator")],
        [ib(t("back", lead.lang), "courses")],
    ])
    text = f"<i>{esc(cat)}</i>\n<b>{esc(name)}</b>\n\n{esc(strip_placeholders(desc))}\n\n{t('price_answer', lead.lang)}"
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


# ------------------------------------------------------------------ FAQ


async def _faq_kb(lang: str) -> InlineKeyboardMarkup | None:
    async with session_scope() as s:
        items = (await s.execute(select(Faq).where(Faq.is_active.is_(True)).order_by(Faq.sort, Faq.asked_count.desc(), Faq.id))).scalars().all()
    if not items:
        return None
    rows = []
    for f in items[:40]:
        q = f.q_ru if lang == "ru" else f.q_uz
        rows.append([ib((q[:60] + "…") if len(q) > 60 else q, f"faq:{f.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.in_(all_button_texts("btn_faq")))
async def faq(msg: TgMessage) -> None:
    lead = await _lead(msg)
    kb = await _faq_kb(lead.lang)
    await msg.answer(t("faq_title", lead.lang) if kb else t("faq_empty", lead.lang), reply_markup=kb)


@router.callback_query(F.data == "faq")
async def faq_cb(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    kb = await _faq_kb(lead.lang)
    await cb.message.edit_text(t("faq_title", lead.lang) if kb else t("faq_empty", lead.lang), reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("faq:"))
async def faq_detail(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    async with session_scope() as s:
        f = await s.get(Faq, int(cb.data.split(":")[1]))
        if f:
            f.asked_count = (f.asked_count or 0) + 1
    if not f:
        await cb.answer()
        return
    q, a = (f.q_ru, f.a_ru) if lead.lang == "ru" else (f.q_uz, f.a_uz)
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(t("operator_btn_inline", lead.lang), "cta:operator")],
                                               [ib(t("back", lead.lang), "faq")]])
    await cb.message.edit_text(f"❓ <b>{esc(q)}</b>\n\n{esc(a)}", reply_markup=kb)
    await cb.answer()


# ------------------------------------------------------------------ materiallar


@router.message(F.text.in_(all_button_texts("btn_materials")))
async def materials(msg: TgMessage) -> None:
    lead = await _lead(msg)
    async with session_scope() as s:
        items = (await s.execute(select(Material).where(Material.is_free.is_(True)).order_by(Material.id.desc()))).scalars().all()
    if not items:
        await msg.answer(t("materials_empty", lead.lang))
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib(f"📄 {m.title[:55]}", f"mat:{m.id}")] for m in items[:40]])
    await msg.answer(t("materials_title", lead.lang), reply_markup=kb)


@router.callback_query(F.data.startswith("mat:"))
async def material_get(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    mid = int(cb.data.split(":")[1])
    await cb.answer()
    if not await require_phone(lead, "after_phone_material", mid):
        return
    await send_material(lead, mid)


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


# ------------------------------------------------------------------ til


@router.message(F.text.in_(all_button_texts("btn_lang")))
async def change_lang(msg: TgMessage) -> None:
    await msg.answer(t("choose_lang", "uz"), reply_markup=lang_kb())


# ------------------------------------------------------------------ bepul dars / operator


@router.message(F.text.in_(all_button_texts("btn_trial")))
async def trial(msg: TgMessage) -> None:
    lead = await _lead(msg)
    if await require_phone(lead, "after_phone_trial"):
        await trial_request(lead)


@router.message(F.text.in_(all_button_texts("btn_operator")))
async def operator(msg: TgMessage) -> None:
    lead = await _lead(msg)
    if await require_phone(lead, "after_phone_operator"):
        await operator_request(lead)


@router.callback_query(F.data.startswith("cta:"))
async def cta(cb: CallbackQuery) -> None:
    lead = await _lead(cb)
    await cb.answer()
    what = cb.data.split(":")[1]
    if what == "trial":
        if await require_phone(lead, "after_phone_trial"):
            await trial_request(lead)
    elif what == "operator":
        if await require_phone(lead, "after_phone_operator"):
            await operator_request(lead)


# ------------------------------------------------------------------ tutor


@router.message(F.text.in_(all_button_texts("btn_tutor")))
async def tutor_on(msg: TgMessage) -> None:
    lead = await _lead(msg)
    if not await settings.get("tutor_enabled"):
        await msg.answer(t("tutor_disabled", lead.lang))
        return
    lead = await update_lead(lead.id, mode="tutor")
    await send_menu(msg.chat.id, lead, t("tutor_intro", lead.lang))


@router.message(F.text.in_(all_button_texts("btn_consultant")))
async def consultant_on(msg: TgMessage) -> None:
    lead = await _lead(msg)
    lead = await update_lead(lead.id, mode="consultant", quiz_state=None)
    await send_menu(msg.chat.id, lead, t("consultant_on", lead.lang))


async def tutor_allowed(lead) -> bool:
    """Kursga qabul qilinganlar — cheksiz; boshqalar — kunlik bepul limit."""
    if lead.status == "accepted":
        return True
    from ...services import worktime

    limit = int(await settings.get("tutor_trial_daily") or 0)
    today = worktime.now_local().date()
    count = lead.tutor_count if lead.tutor_day == today else 0
    return count < limit


async def tutor_consume(lead) -> None:
    from ...services import worktime

    today = worktime.now_local().date()
    count = lead.tutor_count if lead.tutor_day == today else 0
    await update_lead(lead.id, tutor_day=today, tutor_count=count + 1)


@router.message(F.text.in_(all_button_texts("btn_quiz")))
async def quiz_start(msg: TgMessage) -> None:
    lead = await _lead(msg)
    await msg.answer(t("quiz_choose_level", lead.lang), reply_markup=quiz_level_kb(lead.lang))


async def _send_quiz(cb: CallbackQuery, lead, level: str, state: dict | None) -> None:
    if not await tutor_allowed(lead):
        await cb.message.answer(t("tutor_limit", lead.lang, limit=await settings.get("tutor_trial_daily")), reply_markup=cta_kb(lead.lang))
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
    await cb.message.edit_text(f"{t('rating_ask', lead.lang)}\n{'⭐' * val}")
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
