"""Bot uchun umumiy yordamchi funksiyalar."""
from __future__ import annotations

import html
import re

from aiogram.types import Message as TgMessage
from aiogram.types import User as TgUser
from sqlalchemy import select

from ..db import session_scope, utcnow
from ..models import Lead, Source
from ..services import media, settings
from .instance import get_bot
from .keyboards import main_menu
from .texts import t


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        return "+998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    if 10 <= len(digits) <= 15 and (raw or "").strip().startswith("+"):
        return "+" + digits
    return None


def esc(s: str | None) -> str:
    return html.escape(s or "")


async def get_lead(tg_id: int) -> Lead | None:
    async with session_scope() as s:
        return (await s.execute(select(Lead).where(Lead.tg_id == tg_id))).scalars().first()


async def get_or_create_lead(user: TgUser, source_code: str | None = None) -> tuple[Lead, bool]:
    async with session_scope() as s:
        lead = (await s.execute(select(Lead).where(Lead.tg_id == user.id))).scalars().first()
        created = False
        if lead is None:
            source_id = None
            if source_code:
                code = re.sub(r"[^a-zA-Z0-9_\-]", "", source_code)[:64]
                if code:
                    src = (await s.execute(select(Source).where(Source.code == code))).scalars().first()
                    if src is None:
                        src = Source(code=code, name=code)
                        s.add(src)
                        await s.flush()
                    source_id = src.id
            lead = Lead(tg_id=user.id, tg_username=user.username, tg_name=user.full_name,
                        lang="uz", source_id=source_id, onboarding_step="name")
            s.add(lead)
            await s.flush()
            created = True
        else:
            lead.tg_username = user.username
            lead.tg_name = user.full_name
            lead.last_activity = utcnow()
            if lead.is_blocked:
                lead.is_blocked = False
        await s.refresh(lead)
        return lead, created


async def update_lead(lead_id: int, **values) -> Lead:
    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        for k, v in values.items():
            setattr(lead, k, v)
        await s.flush()
        await s.refresh(lead)
        return lead


async def send_menu(chat_id: int, lead: Lead, text: str | None = None) -> None:
    tutor_enabled = bool(await settings.get("tutor_enabled"))
    await get_bot().send_message(chat_id, text or t("menu", lead.lang), reply_markup=main_menu(lead, tutor_enabled))


def strip_placeholders(text: str) -> str:
    """[TO'LDIRILSIN] qatorlarini foydalanuvchiga ko'rsatmaymiz."""
    lines = [ln for ln in (text or "").splitlines() if "TO'LDIRILSIN" not in ln.upper() and "TO‘LDIRILSIN" not in ln.upper()]
    return "\n".join(lines).strip()


async def save_incoming(msg: TgMessage) -> dict | str:
    """Kiruvchi xabarni tahlil qiladi va faylni yuklab oladi.
    Qaytaradi: dict(kind, text, file_path, file_name, mime, size) yoki xato matni kaliti."""
    kind = "text"
    file_id = None
    file_name = None
    mime = None
    size = None
    text = msg.text or msg.caption
    if msg.photo:
        kind, ph = "photo", msg.photo[-1]
        file_id, size, mime, file_name = ph.file_id, ph.file_size, "image/jpeg", "photo.jpg"
    elif msg.voice:
        kind, file_id, size = "voice", msg.voice.file_id, msg.voice.file_size
        mime, file_name = msg.voice.mime_type or "audio/ogg", "voice.ogg"
    elif msg.audio:
        kind, file_id, size = "audio", msg.audio.file_id, msg.audio.file_size
        mime, file_name = msg.audio.mime_type, msg.audio.file_name or "audio.mp3"
    elif msg.video:
        kind, file_id, size = "video", msg.video.file_id, msg.video.file_size
        mime, file_name = msg.video.mime_type or "video/mp4", msg.video.file_name or "video.mp4"
    elif msg.video_note:
        kind, file_id, size = "video_note", msg.video_note.file_id, msg.video_note.file_size
        mime, file_name = "video/mp4", "video_note.mp4"
    elif msg.animation:
        kind, file_id, size = "video", msg.animation.file_id, msg.animation.file_size
        mime, file_name = msg.animation.mime_type or "video/mp4", msg.animation.file_name or "animation.mp4"
    elif msg.document:
        kind, file_id, size = "document", msg.document.file_id, msg.document.file_size
        mime, file_name = msg.document.mime_type, msg.document.file_name or "file"
        if (mime or "").startswith("image/") and not (mime or "").endswith("gif"):
            kind = "photo"
    elif msg.sticker:
        return {"kind": "text", "text": f"[stiker {msg.sticker.emoji or ''}]", "file_path": None,
                "file_name": None, "mime": None, "size": None}
    elif not msg.text:
        return "unsupported"

    path = None
    if file_id:
        limit = min(await media.limit_mb(kind), media.TELEGRAM_DOWNLOAD_LIMIT_MB)
        if size and size > limit * 1024 * 1024:
            return f"too_big:{limit}"
        path = media.new_path(media.guess_ext(file_name, mime, ".bin"))
        await get_bot().download(file_id, destination=path)
        size = size or path.stat().st_size
    return {"kind": kind, "text": text, "file_path": str(path) if path else None, "file_name": file_name,
            "mime": mime, "size": size}
