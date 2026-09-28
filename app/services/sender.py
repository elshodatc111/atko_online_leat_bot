"""Leadga bot orqali xabar yuborish (bloklanganini aniqlash bilan)."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import FSInputFile

from ..db import session_scope
from ..models import Lead

log = logging.getLogger(__name__)


async def _mark_blocked(tg_id: int) -> None:
    from sqlalchemy import update

    async with session_scope() as s:
        await s.execute(update(Lead).where(Lead.tg_id == tg_id).values(is_blocked=True))


async def send_text(tg_id: int, text: str, reply_markup=None) -> int | None:
    from ..bot.instance import get_bot

    try:
        m = await get_bot().send_message(tg_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
        return m.message_id
    except TelegramForbiddenError:
        await _mark_blocked(tg_id)
        return None
    except TelegramBadRequest as e:
        # HTML xatosi bo'lsa — oddiy matn sifatida
        if "parse" in str(e).lower() or "entities" in str(e).lower():
            m = await get_bot().send_message(tg_id, text, reply_markup=reply_markup, parse_mode=None)
            return m.message_id
        log.warning("send_text xatosi: %s", e)
        return None


async def send_file(tg_id: int, kind: str, path: Path, caption: str | None = None, file_name: str | None = None,
                    reply_markup=None) -> str | None:
    """Faylni yuboradi. Qaytaradi: Telegram file_id (qayta ishlatish uchun) yoki None."""
    from ..bot.instance import get_bot

    bot = get_bot()
    f = FSInputFile(path, filename=file_name or path.name)
    try:
        if kind == "photo":
            m = await bot.send_photo(tg_id, f, caption=caption, reply_markup=reply_markup)
            return m.photo[-1].file_id if m.photo else None
        if kind == "voice":
            m = await bot.send_voice(tg_id, f, caption=caption, reply_markup=reply_markup)
            return m.voice.file_id if m.voice else None
        if kind == "audio":
            m = await bot.send_audio(tg_id, f, caption=caption, reply_markup=reply_markup)
            return m.audio.file_id if m.audio else None
        if kind == "video":
            m = await bot.send_video(tg_id, f, caption=caption, reply_markup=reply_markup)
            return m.video.file_id if m.video else None
        m = await bot.send_document(tg_id, f, caption=caption, reply_markup=reply_markup)
        return m.document.file_id if m.document else None
    except TelegramForbiddenError:
        await _mark_blocked(tg_id)
        raise
