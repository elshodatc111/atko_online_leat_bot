"""Operator chatlari: so'rov, olish ("Menga ochdim"), o'tkazish, yopish, xabarlar."""
from __future__ import annotations

import asyncio
import html
import logging
import re
from pathlib import Path

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from ..db import session_scope, utcnow
from ..models import Chat, Lead, Message, Staff
from . import audit, media, sender, settings, worktime
from .notify import hub, telegram_staff

log = logging.getLogger(__name__)

REASON_LABELS = {
    "user": "Foydalanuvchi so'rovi",
    "ai": "AI yo'naltirdi",
    "user_request": "Foydalanuvchi so'rovi",
    "complaint": "⚠️ Shikoyat",
    "payment": "💳 To'lov masalasi",
    "ready_to_enroll": "🔥 Kursga yozilishga tayyor",
    "complex": "Murakkab savol",
    "trial": "🎁 Bepul darsga yozilish",
    "enroll": "📝 Tarifga yozilmoqchi",
}


class ChatError(Exception):
    pass


_lock = asyncio.Lock()  # bir vaqtda ikki operator bitta chatni olmasligi uchun


def plain(text: str | None) -> str | None:
    """AI/bot javobidagi HTML teg va Markdown belgilarini panel uchun olib tashlaydi."""
    if not text:
        return text
    return html.unescape(re.sub(r"<[^>]+>", "", text)).replace("**", "")


def message_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "chat_id": m.chat_id,
        "lead_id": m.lead_id,
        "sender": m.sender,
        "staff": m.staff.display_name if m.staff else None,
        "kind": m.kind,
        "text": plain(m.text) if m.sender in ("ai", "bot") else m.text,
        "file_url": f"/media/{media.rel(m.file_path)}" if m.file_path else None,
        "file_name": m.file_name,
        "mime": m.mime,
        "transcript": m.transcript,
        "time": worktime.fmt(m.created_at, "%H:%M"),
        "date": worktime.fmt(m.created_at, "%d.%m.%Y"),
    }


def chat_dict(c: Chat) -> dict:
    lead = c.lead
    return {
        "id": c.id,
        "lead_id": c.lead_id,
        "lead_name": lead.display if lead else "",
        "phone": lead.phone if lead else None,
        "status": c.status,
        "operator_id": c.operator_id,
        "operator": c.operator.display_name if c.operator else None,
        "operator_full": c.operator.full_name if c.operator else None,
        "reason": REASON_LABELS.get(c.reason, c.reason),
        "off_hours": c.off_hours,
        "requested": worktime.fmt(c.requested_at, "%d.%m %H:%M"),
        "unread": c.unread,
    }


async def active_chat(s, lead_id: int) -> Chat | None:
    return (await s.execute(select(Chat).where(Chat.lead_id == lead_id, Chat.status.in_(("waiting", "active")))
                            .order_by(Chat.id.desc()).limit(1))).scalars().first()


async def add_message(lead_id: int, sender: str, *, chat_id: int | None = None, text: str | None = None,
                      kind: str = "text", staff_id: int | None = None, mode: str | None = None,
                      file_path: str | None = None, file_name: str | None = None, mime: str | None = None,
                      file_size: int | None = None, transcript: str | None = None, emit: bool = True) -> Message:
    async with session_scope() as s:
        m = Message(lead_id=lead_id, chat_id=chat_id, sender=sender, text=text, kind=kind, staff_id=staff_id,
                    mode=mode, file_path=file_path, file_name=file_name, mime=mime, file_size=file_size,
                    transcript=transcript)
        s.add(m)
        await s.flush()
        await s.refresh(m, ["staff"])
        mid = m.id
    if emit:
        async with session_scope() as s:
            m = await s.get(Message, mid)
            chat = await s.get(Chat, chat_id) if chat_id else None
        data = message_dict(m)
        data["operator_id"] = chat.operator_id if chat else None
        await hub.emit("message", data)
    return m


async def request_operator(lead_id: int, reason: str = "user", note: str | None = None) -> tuple[Chat, bool, bool]:
    """Operator so'rovini yaratadi. Qaytaradi: (chat, yangi_yaratildimi, ish_vaqtidan_tashqarimi)."""
    working = await worktime.is_working_time()
    async with session_scope() as s:
        existing = await active_chat(s, lead_id)
        if existing:
            return existing, False, existing.off_hours
        sla_start = utcnow() if working else worktime.local_to_utc_naive(await worktime.next_opening())
        chat = Chat(lead_id=lead_id, reason=reason, off_hours=not working, sla_start=sla_start,
                    opened_notified=working)
        s.add(chat)
        await s.flush()
        chat_id = chat.id
        lead = await s.get(Lead, lead_id)
        lead_name = lead.display if lead else ""
        phone = lead.phone if lead else None
    label = REASON_LABELS.get(reason, reason)
    sys_text = f"Operator so'rovi: {label}" + (f"\n{note}" if note else "")
    await add_message(lead_id, "system", chat_id=chat_id, text=sys_text)
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        data = chat_dict(chat)
    await hub.emit("chat_new", data)
    if working:
        await telegram_staff(
            f"🔔 <b>Yangi murojaat!</b>\n👤 {html.escape(lead_name)}\n📱 {phone or '—'}\n📌 {label}"
            + (f"\n📝 {html.escape(note[:300])}" if note else ""),
            online_operators=True, path=f"/chats/{chat_id}",
        )
    # AI xulosa (fonda)
    from . import ai

    asyncio.create_task(_summary_bg(lead_id, chat_id))
    return chat, True, not working


async def _summary_bg(lead_id: int, chat_id: int) -> None:
    from . import ai

    try:
        data = await ai.summarize_lead(lead_id)
        if data:
            await hub.emit("lead_summary", {"lead_id": lead_id, "chat_id": chat_id, "summary": data.get("summary"),
                                            "temperature": data.get("temperature")})
    except Exception as e:  # noqa: BLE001
        log.debug("summary bg: %s", e)


async def operator_load(s, staff_id: int) -> int:
    return (await s.execute(select(func.count(Chat.id)).where(Chat.operator_id == staff_id,
                                                             Chat.status == "active"))).scalar_one()


async def claim(chat_id: int, staff: Staff) -> Chat:
    from ..bot.texts import t

    max_chats = int(await settings.get("max_chats_per_operator") or 5)
    async with _lock:
        return await _claim(chat_id, staff, max_chats)


async def _claim(chat_id: int, staff: Staff, max_chats: int) -> Chat:
    from ..bot.texts import t

    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        if not chat:
            raise ChatError("Chat topilmadi")
        if chat.status != "waiting" or chat.operator_id:
            who = chat.operator.display_name if chat.operator else ""
            raise ChatError(f"Bu chatni allaqachon {who} oldi" if who else "Chat mavjud emas")
        if await operator_load(s, staff.id) >= max_chats:
            raise ChatError(f"Sizda {max_chats} ta faol chat bor (limit). Avval birini yoping.")
        chat.operator_id = staff.id
        chat.status = "active"
        chat.accepted_at = utcnow()
        chat.unread = 0
        lead = await s.get(Lead, chat.lead_id)
        lead.last_operator_id = staff.id
        lead.mode = "consultant"
        if lead.status == "new":
            lead.status = "contacted"
        tg_id, lang, lead_id = lead.tg_id, lead.lang, lead.id
        await audit.log(staff.id, "chat_claim", "chat", chat_id, f"Lead #{lead_id}", session=s)
    await sender.send_text(tg_id, t("operator_connected", lang, operator=html.escape(staff.display_name)))
    await add_message(lead_id, "system", chat_id=chat_id, text=f"{staff.display_name} chatni oldi")
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        data = chat_dict(chat)
    await hub.emit("chat_claimed", data)
    return chat


async def transfer(chat_id: int, staff: Staff, to_staff_id: int) -> Chat:
    from ..bot.texts import t

    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        if not chat or chat.status == "closed":
            raise ChatError("Chat topilmadi yoki yopilgan")
        if chat.operator_id != staff.id and not staff.is_admin:
            raise ChatError("Faqat chatni olgan operator yoki admin o'tkaza oladi")
        target = await s.get(Staff, to_staff_id)
        if not target or not target.is_active:
            raise ChatError("Operator topilmadi")
        if target.id == chat.operator_id:
            raise ChatError("Chat allaqachon shu operatorda")
        max_chats = int(await settings.get("max_chats_per_operator") or 5)
        if await operator_load(s, target.id) >= max_chats:
            raise ChatError(f"{target.display_name} da {max_chats} ta faol chat bor (limit)")
        old = chat.operator.display_name if chat.operator else "navbat"
        chat.operator_id = target.id
        chat.status = "active"
        chat.accepted_at = chat.accepted_at or utcnow()
        chat.transfers = (chat.transfers or 0) + 1
        chat.idle_alert_sent = False
        lead = await s.get(Lead, chat.lead_id)
        lead.last_operator_id = target.id
        tg_id, lang, lead_id, lead_name = lead.tg_id, lead.lang, lead.id, lead.display
        target_name, target_tg = target.display_name, target.tg_id
        await audit.log(staff.id, "chat_transfer", "chat", chat_id, f"{old} → {target_name}", session=s)
    await sender.send_text(tg_id, t("operator_connected", lang, operator=html.escape(target_name)))
    await add_message(lead_id, "system", chat_id=chat_id, text=f"Chat {old} → {target_name} ga o'tkazildi ({staff.display_name})")
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        data = chat_dict(chat)
    await hub.emit("chat_transferred", data)
    await telegram_staff(f"🔁 Sizga chat o'tkazildi: <b>{html.escape(lead_name)}</b> ({html.escape(staff.display_name)} dan)",
                         staff_ids=[to_staff_id], path=f"/chats/{chat_id}")
    return chat


def rating_kb(chat_id: int) -> InlineKeyboardMarkup:
    # bitta qatorda 5 ta ixcham tugma
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{i}⭐", callback_data=f"rate:{chat_id}:{i}") for i in range(1, 6)],
    ])


async def close(chat_id: int, staff: Staff | None, silent: bool = False) -> Chat:
    from ..bot.texts import t

    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        if not chat or chat.status == "closed":
            raise ChatError("Chat topilmadi yoki allaqachon yopilgan")
        if staff and chat.operator_id not in (None, staff.id) and not staff.is_admin:
            raise ChatError("Faqat chatni olgan operator yoki admin yopa oladi")
        op = chat.operator or staff
        op_name = op.display_name if op else "ATKO"
        was_active = chat.status == "active"
        chat.status = "closed"
        chat.closed_at = utcnow()
        chat.closed_by_id = staff.id if staff else None
        lead = await s.get(Lead, chat.lead_id)
        tg_id, lang, lead_id = lead.tg_id, lead.lang, lead.id
        if was_active and not silent:
            lead.pending_input = "rating"
            lead.pending_ref = chat_id
        if staff:
            await audit.log(staff.id, "chat_close", "chat", chat_id, f"Lead #{lead_id}", session=s)
    if not silent:
        await sender.send_text(tg_id, t("chat_closed", lang, operator=html.escape(op_name)))
        if was_active:
            await sender.send_text(tg_id, t("rating_ask", lang), reply_markup=rating_kb(chat_id))
    await add_message(lead_id, "system", chat_id=chat_id,
                      text=f"Chat yopildi ({staff.display_name if staff else 'tizim'})")
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        data = chat_dict(chat)
    await hub.emit("chat_closed", data)
    return chat


def operator_header(staff: Staff) -> str:
    """Leadga boradigan har bir operator xabari tepasida kim yozgani."""
    return f"👨‍💼 <b>{html.escape(staff.display_name)}</b> · <i>ATKO</i>\n┄┄┄┄┄┄┄┄┄┄┄┄\n"


async def _check_writer(chat_id: int, staff: Staff) -> Chat:
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
    if not chat or chat.status != "active":
        raise ChatError("Chat faol emas. Avval «Menga ochdim» tugmasini bosing.")
    if chat.operator_id != staff.id and not staff.is_admin:
        raise ChatError(f"Bu chat bilan {chat.operator.display_name if chat.operator else 'boshqa operator'} suhbatlashmoqda")
    return chat


async def _after_operator_msg(chat_id: int) -> None:
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        now = utcnow()
        chat.last_operator_msg_at = now
        chat.first_response_at = chat.first_response_at or now
        chat.idle_alert_sent = False
        chat.unread = 0


async def operator_send_text(chat_id: int, staff: Staff, text: str) -> Message:
    chat = await _check_writer(chat_id, staff)
    text = text.strip()
    if not text:
        raise ChatError("Bo'sh xabar")
    lead = chat.lead
    mid = await sender.send_text(lead.tg_id, operator_header(staff) + html.escape(text))
    if mid is None:
        raise ChatError("Xabar yetkazilmadi: foydalanuvchi botni bloklagan bo'lishi mumkin")
    await _after_operator_msg(chat_id)
    return await add_message(lead.id, "operator", chat_id=chat_id, text=text, staff_id=staff.id, mode="consultant")


async def operator_send_file(chat_id: int, staff: Staff, path: Path, file_name: str, mime: str | None,
                             caption: str | None = None, as_voice: bool = False) -> Message:
    chat = await _check_writer(chat_id, staff)
    lead = chat.lead
    kind = "voice" if as_voice else media.media_kind_from_mime(mime, file_name)
    send_path, send_kind = path, kind
    if as_voice:
        if path.suffix.lower() not in (".ogg", ".oga"):
            conv = await media.to_ogg_opus(path)
            if conv:
                send_path = conv
            else:
                send_kind = "document"  # ffmpeg yo'q — audio fayl sifatida
    elif kind == "audio" and path.suffix.lower() not in (".mp3", ".m4a"):
        send_kind = "document"
    try:
        cap = operator_header(staff) + (html.escape(caption) if caption else "")
        await sender.send_file(lead.tg_id, send_kind, send_path, caption=cap.rstrip()[:1024], file_name=file_name)
    except TelegramForbiddenError:
        raise ChatError("Foydalanuvchi botni bloklagan")
    except Exception as e:  # noqa: BLE001
        raise ChatError(f"Fayl yuborilmadi: {e}")
    await _after_operator_msg(chat_id)
    return await add_message(lead.id, "operator", chat_id=chat_id, text=caption, kind=kind, staff_id=staff.id,
                             mode="consultant", file_path=str(send_path), file_name=file_name, mime=mime,
                             file_size=send_path.stat().st_size)


async def on_lead_message(lead_id: int, chat_id: int) -> None:
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        if chat:
            chat.last_lead_msg_at = utcnow()
            chat.unread = (chat.unread or 0) + 1
