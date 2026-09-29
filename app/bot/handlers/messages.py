"""Barcha boshqa xabarlar: operator chatiga uzatish, AI konsultant, AI tutor."""
from __future__ import annotations

import asyncio
import html
import logging
import re

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message as TgMessage

from ...db import session_scope
from ...models import FORMATS, GOALS, Chat
from ...services import ai, settings
from ...services import chats as chat_svc
from ...services.notify import hub, telegram_staff
from ..actions import operator_request, run_pending_after_phone
from ..common import get_lead, get_or_create_lead, normalize_phone, save_incoming, send_menu, update_lead
from ..keyboards import cta_kb
from ..middlewares import mark_stored
from ..texts import t
from .menu import tutor_allowed, tutor_consume
from .start import handle_onboarding_text

log = logging.getLogger(__name__)
router = Router(name="messages")

PRICE_RE = re.compile(r"narx|necha pul|qancha|to'lov|tolov|стоим|цен|сколько|оплат|price", re.I)


async def _transcribe_bg(msg_id: int, path: str, lang: str) -> None:
    text = await ai.transcribe(path, lang)
    if not text:
        return
    from ...models import Message

    async with session_scope() as s:
        m = await s.get(Message, msg_id)
        if m:
            m.transcript = text
    await hub.emit("transcript", {"id": msg_id, "transcript": text})


@router.message(F.chat.type == "private")
async def any_message(msg: TgMessage) -> None:
    lead = await get_lead(msg.from_user.id)
    if lead is None:
        lead, _ = await get_or_create_lead(msg.from_user)
    else:
        lead = await update_lead(lead.id, is_blocked=False, tg_username=msg.from_user.username)

    # 1) Ro'yxatdan o'tish bosqichlari
    if lead.onboarding_step and msg.text:
        if await handle_onboarding_text(msg, lead):
            return
        lead = await get_lead(msg.from_user.id)

    # 2) Telefon kutilayotgan bo'lsa va raqamni qo'lda yozgan bo'lsa
    if lead.pending_input and lead.pending_input.startswith("after_phone") and msg.text:
        phone = normalize_phone(msg.text)
        if phone:
            lead = await update_lead(lead.id, phone=phone)
            await run_pending_after_phone(lead)
            return

    # 3) Baho izohi
    if lead.pending_input == "rating_comment" and msg.text:
        chat_id = lead.pending_ref
        async with session_scope() as s:
            chat = await s.get(Chat, chat_id) if chat_id else None
            if chat:
                chat.rating_comment = msg.text[:1000]
                rating = chat.rating
                op_name = chat.operator.display_name if chat.operator else "—"
        lead = await update_lead(lead.id, pending_input=None, pending_ref=None)
        await send_menu(msg.chat.id, lead, t("rating_thanks", lead.lang))
        if chat:
            await hub.emit("chat_rated", {"chat_id": chat_id, "rating": rating, "comment": msg.text[:1000]})
            if rating and rating <= 2:
                await telegram_staff(f"💬 Past baho izohi ({'⭐' * rating}, {html.escape(op_name)}):\n{html.escape(msg.text[:800])}",
                                     admins=True, path=f"/chats/{chat_id}")
        return
    if lead.pending_input == "rating_comment":
        await update_lead(lead.id, pending_input=None, pending_ref=None)

    # 4) Faylni yuklab olish / tekshirish
    data = await save_incoming(msg)
    if isinstance(data, str):
        if data.startswith("too_big:"):
            await msg.answer(t("file_too_big", lead.lang, mb=data.split(":")[1]))
        else:
            await msg.answer(t("unsupported", lead.lang))
        return

    # 5) Operator bilan chat (kutilmoqda yoki faol)
    async with session_scope() as s:
        chat = await chat_svc.active_chat(s, lead.id)
        chat_id = chat.id if chat else None
        chat_status = chat.status if chat else None
        off_hours = chat.off_hours if chat else False
    mode = "consultant" if chat_status == "active" else lead.mode
    stored = await chat_svc.add_message(
        lead.id, "lead", chat_id=chat_id, text=data["text"], kind=data["kind"], mode=mode,
        file_path=data["file_path"], file_name=data["file_name"], mime=data["mime"], file_size=data["size"],
    )
    mark_stored(msg)
    if data["kind"] in ("voice", "audio", "video_note") and data["file_path"]:
        task = asyncio.create_task(_transcribe_bg(stored.id, data["file_path"], lead.lang))
    else:
        task = None

    if chat_id:
        await chat_svc.on_lead_message(lead.id, chat_id)
        if chat_status == "active" or (not off_hours and lead.mode != "tutor"):
            return  # operator javob beradi, AI jim turadi (AI mentor rejimida navbatda turganda ham mentor javob beradi)
        # ish vaqtidan tashqari navbatda — AI javob beradi (pastda)

    # 6) AI javobi
    text = data["text"]
    if data["kind"] in ("voice", "audio", "video_note"):
        if task:
            await task
        async with session_scope() as s:
            from ...models import Message

            m = await s.get(Message, stored.id)
            text = m.transcript if m else None
        if not text:
            await msg.answer(t("ai_unavailable", lead.lang), reply_markup=cta_kb(lead.lang, buy=False))
            return
    image = data["file_path"] if data["kind"] == "photo" else None
    if not text and not image:
        if data["kind"] in ("document", "video"):
            await msg.answer(t("unsupported", lead.lang))
        return

    if lead.mode == "tutor" and chat_status != "active":
        await _tutor(msg, lead, text, image, stored.id)
    else:
        await _consultant(msg, lead, text, image, stored.id, chat_id)


async def _typing(msg: TgMessage) -> None:
    try:
        await msg.bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
    except Exception:  # noqa: BLE001
        pass


async def _send_ai(msg: TgMessage, lead, text: str, reply_markup=None) -> None:
    body = ai.to_telegram_html(text)
    # Telegram limiti 4096 belgi
    parts = [body[i : i + 3900] for i in range(0, len(body), 3900)] or [""]
    for i, part in enumerate(parts):
        kb = reply_markup if i == len(parts) - 1 else None
        try:
            await msg.answer(part, reply_markup=kb)
        except Exception:  # noqa: BLE001
            await msg.answer(html.unescape(re.sub(r"<[^>]+>", "", part)), reply_markup=kb, parse_mode=None)


async def _consultant(msg: TgMessage, lead, text: str | None, image: str | None, stored_id: int, chat_id: int | None) -> None:
    if not await ai.is_available():
        if text and PRICE_RE.search(text):
            from .menu import _courses_kb

            await msg.answer(t("courses_title", lead.lang) + "\n\n" + t("price_note", lead.lang),
                             reply_markup=await _courses_kb(lead.lang))
        else:
            await msg.answer(t("ai_unavailable", lead.lang), reply_markup=cta_kb(lead.lang))
        return
    await _typing(msg)
    try:
        res = await ai.consultant_reply(lead, text, image, exclude_id=stored_id)
    except Exception as e:  # noqa: BLE001
        log.warning("AI konsultant xatosi: %s", e)
        await msg.answer(t("ai_unavailable", lead.lang), reply_markup=cta_kb(lead.lang))
        return

    # lead ma'lumotlarini yangilash
    upd = {}
    for k, v in res.lead_updates.items():
        if k == "goal" and v in GOALS and not lead.goal:
            upd["goal"] = v
        elif k == "study_format" and v in FORMATS:
            upd["study_format"] = v
        elif k == "temperature" and v in ("hot", "warm", "cold"):
            upd["temperature"] = v
        elif k in ("name",) and not lead.name:
            upd["name"] = str(v)[:64]
        elif k in ("level", "city", "interested_tariff"):
            upd[k] = str(v)[:120]
    if upd:
        lead = await update_lead(lead.id, **upd)
        await hub.emit("lead_updated", {"lead_id": lead.id})
    kb = None
    escalate = res.escalate and await settings.get("ai_auto_escalate") and not chat_id
    if res.unanswered and not escalate:
        kb = cta_kb(lead.lang, buy=False)
    if res.text:
        await _send_ai(msg, lead, res.text, kb)
        await chat_svc.add_message(lead.id, "ai", chat_id=chat_id, text=res.text, mode="consultant")
    if escalate:
        reason = res.escalate.get("reason") or "complex"
        note = res.escalate.get("summary")
        if not lead.phone:
            from ..actions import require_phone

            await require_phone(lead, "after_phone_operator")
            return
        await operator_request(lead, reason=reason, note=note)


async def _tutor(msg: TgMessage, lead, text: str | None, image: str | None, stored_id: int) -> None:
    if not await settings.get("tutor_enabled"):
        lead = await update_lead(lead.id, mode="consultant")
        await send_menu(msg.chat.id, lead, t("tutor_disabled", lead.lang))
        return
    if not await tutor_allowed(lead):
        await msg.answer(t("tutor_limit", lead.lang, limit=await settings.get("tutor_trial_daily")), reply_markup=cta_kb(lead.lang, operator=False))
        return
    if not await ai.is_available():
        await msg.answer(t("ai_unavailable", lead.lang))
        return
    await _typing(msg)
    try:
        from ...services import subscriptions

        answer = await ai.tutor_reply(lead, text, image, exclude_id=stored_id, is_student=await subscriptions.is_active(lead.tg_id))
    except Exception as e:  # noqa: BLE001
        log.warning("AI tutor xatosi: %s", e)
        await msg.answer(t("ai_unavailable", lead.lang))
        return
    await tutor_consume(lead)
    await _send_ai(msg, lead, answer)
    await chat_svc.add_message(lead.id, "ai", text=answer, mode="tutor", emit=False)
