"""Leadning HAR BIR xabari va tugma bosishini suhbat tarixiga yozib boruvchi middleware.

Oddiy matn/fayllarni `messages.any_message` o'zi saqlaydi (fayl yuklab olinadi, transkripsiya qilinadi).
Qolgan hamma narsa — menyu tugmalari, ro'yxatdan o'tish javoblari (ism), kontakt, buyruqlar,
inline tugmalar (tarif, bepul dars, baho...), baho izohi, rad etilgan katta fayllar — shu yerda yoziladi.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message as TgMessage, TelegramObject
from sqlalchemy import select

from ..db import session_scope
from ..models import Lead, Staff
from ..services import chats as chat_svc

log = logging.getLogger(__name__)

# any_message tomonidan saqlangan xabarlar (chat_id, message_id)
_stored: "OrderedDict[tuple[int, int], None]" = OrderedDict()

KIND_LABELS = {
    "photo": "🖼 Rasm", "voice": "🎙 Ovozli xabar", "audio": "🎵 Audio", "video": "🎬 Video",
    "video_note": "⏺ Video xabar", "document": "📎 Fayl", "sticker": "Stiker", "animation": "GIF",
    "location": "📍 Joylashuv", "poll": "📊 So'rovnoma",
}


def mark_stored(msg: TgMessage) -> None:
    _stored[(msg.chat.id, msg.message_id)] = None
    while len(_stored) > 5000:
        _stored.popitem(last=False)


def _was_stored(msg: TgMessage) -> bool:
    return _stored.pop((msg.chat.id, msg.message_id), 0) is None


def _menu_texts() -> set[str]:
    from .texts import TEXTS

    out: set[str] = set()
    for key, val in TEXTS.items():
        if key.startswith("btn_") or key in ("later", "skip"):
            out.update(v for v in val.values() if v)
    return out


def _message_text(msg: TgMessage) -> str:
    if msg.contact:
        return f"📱 Kontakt yubordi: {msg.contact.phone_number}"
    if msg.text:
        return msg.text
    for kind, label in KIND_LABELS.items():
        if getattr(msg, kind, None):
            extra = ""
            if kind == "document" and msg.document and msg.document.file_name:
                extra = f" ({msg.document.file_name})"
            if kind == "sticker" and msg.sticker and msg.sticker.emoji:
                extra = f" {msg.sticker.emoji}"
            cap = f"\n{msg.caption}" if msg.caption else ""
            return f"{label}{extra}{cap}"
    return msg.caption or "[xabar]"


def _button_text(cb: CallbackQuery) -> str:
    try:
        markup = cb.message.reply_markup if cb.message else None
        for row in (markup.inline_keyboard if markup else []):
            for btn in row:
                if btn.callback_data == cb.data:
                    return btn.text
    except Exception:  # noqa: BLE001
        pass
    return _fallback_label(cb.data or "")


def _fallback_label(data: str) -> str:
    """Tugma matni topilmasa — callback ma'lumotidan o'qiladigan nom."""
    from ..models import FORMATS, GOALS

    key, _, val = data.partition(":")
    fixed = {
        "lang": {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский"},
        "goal": {k: v["uz"] for k, v in GOALS.items()} | {"skip": "⏭ O'tkazib yuborish"},
        "fmt": {k: v["uz"] for k, v in FORMATS.items()} | {"skip": "⏭ O'tkazib yuborish"},
        "cta": {"operator": "👨‍💼 Operator bilan bog'lanish"},
    }
    if key in fixed:
        return fixed[key].get(val, data)
    if key == "rate":
        parts = data.split(":")
        return "⭐" * int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else data
    labels = {"tariff": "📚 Tarif", "info": "ℹ️ Ma'lumot", "quiz": "📝 Mini-test", "rate_skip": "⏭ Bahoga izohsiz",
              "courses": "⬅️ Tariflar ro'yxati", "buy": "💳 Obuna sotib olish", "plan": "💳 Obuna varianti",
              "enroll": "👨‍💼 Admin bilan bog'lanish (tarif)", "sublink": "🔗 Guruh havolasi"}
    return f"{labels.get(key, key)} {val}".strip()


def _skip(text: str) -> bool:
    """Xodimlarning login/taklif xabarlari lead tarixiga yozilmaydi."""
    t = text or ""
    return (t.startswith("/start login_") or t.startswith("/start inv_") or t.startswith("login_ok:")
            or t.startswith("login_no:") or t.startswith("/myid") or t.startswith("/panel"))


async def _lead(tg_id: int) -> Lead | None:
    async with session_scope() as s:
        return (await s.execute(select(Lead).where(Lead.tg_id == tg_id))).scalars().first()


async def log_lead_event(tg_id: int, text: str) -> None:
    lead = await _lead(tg_id)
    if not lead:
        return
    async with session_scope() as s:
        chat = await chat_svc.active_chat(s, lead.id)
        chat_id = chat.id if chat else None
    await chat_svc.add_message(lead.id, "lead", chat_id=chat_id, text=text[:4000],
                               mode="consultant" if chat_id else lead.mode)
    if chat_id:
        await chat_svc.on_lead_message(lead.id, chat_id)


class LeadHistoryMiddleware(BaseMiddleware):
    """Outer middleware: har bir kiruvchi xabar va tugma bosish tarixga tushadi."""

    def __init__(self) -> None:
        self.menu = _menu_texts()

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, CallbackQuery):
            if event.message and getattr(event.message.chat, "type", "private") == "private" and not _skip(event.data or ""):
                # tugma bosilishi — oldin yozamiz (tarixda to'g'ri tartibda chiqishi uchun)
                try:
                    await log_lead_event(event.from_user.id, f"🔘 {_button_text(event)}")
                except Exception:  # noqa: BLE001
                    log.exception("Tugma bosishini yozib bo'lmadi")
            return await handler(event, data)

        if not isinstance(event, TgMessage) or event.chat.type != "private" or not event.from_user:
            return await handler(event, data)

        text = _message_text(event)
        if _skip(text):
            return await handler(event, data)

        pre = bool(event.contact) or (event.text or "") in self.menu or (event.text or "").startswith("/")
        if pre:
            # menyu tugmasi, kontakt, buyruq — handler'dan OLDIN yozamiz (operator so'rovi va h.k. dan oldin chiqadi).
            # Birinchi /start da lead hali yo'q — u holda handler'dan keyin yozamiz.
            existed = False
            try:
                existed = await _lead(event.from_user.id) is not None
                if existed:
                    await log_lead_event(event.from_user.id, text)
            except Exception:  # noqa: BLE001
                log.exception("Lead xabarini yozib bo'lmadi")
            try:
                return await handler(event, data)
            finally:
                if not existed:
                    try:
                        await log_lead_event(event.from_user.id, text)
                    except Exception:  # noqa: BLE001
                        log.exception("Lead xabarini yozib bo'lmadi")
        try:
            return await handler(event, data)
        finally:
            try:
                if not _was_stored(event):
                    await log_lead_event(event.from_user.id, text)
            except Exception:  # noqa: BLE001
                log.exception("Lead xabarini yozib bo'lmadi")


class PhoneGateMiddleware(BaseMiddleware):
    """Telefon raqam tasdiqlanmaguncha botning bo'limlari yopiq (faqat til, ism va kontakt yuborish mumkin)."""

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        from .keyboards import contact_kb
        from .texts import all_button_texts, t

        user = getattr(event, "from_user", None)
        if isinstance(event, TgMessage):
            if event.chat.type != "private" or not user:
                return await handler(event, data)
            txt = event.text or ""
            if event.contact or txt.startswith("/") or txt in all_button_texts("btn_lang"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if not user or (event.data or "").startswith(("lang:", "login_")):
                return await handler(event, data)
            if event.message and getattr(event.message.chat, "type", "private") != "private":
                return await handler(event, data)
        else:
            return await handler(event, data)
        lead = await _lead(user.id)
        if lead is None or lead.phone:
            return await handler(event, data)
        if isinstance(event, TgMessage) and lead.onboarding_step in ("lang", "name"):
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:  # noqa: BLE001
                pass
        from .instance import get_bot

        await get_bot().send_message(user.id, t("phone_required", lead.lang), reply_markup=contact_kb(lead.lang))
        return None
