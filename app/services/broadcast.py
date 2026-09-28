"""Ommaviy xabar yuborish: barcha / kursga qabul qilinganlar / qabul qilinmaganlar."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import FSInputFile
from sqlalchemy import select

from ..db import session_scope, utcnow
from ..models import Broadcast, Lead
from .notify import hub

log = logging.getLogger(__name__)

SEGMENTS = {
    "all": "Barcha foydalanuvchilar",
    "accepted": "Kursga qabul qilinganlar",
    "not_accepted": "Kursga qabul qilinmaganlar",
}
KINDS = {"text": "Matn", "photo": "Matn + rasm", "video": "Matn + video"}

_running: dict[int, asyncio.Task] = {}


async def recipients(segment: str) -> list[int]:
    async with session_scope() as s:
        q = select(Lead.tg_id).where(Lead.is_blocked.is_(False))
        if segment == "accepted":
            q = q.where(Lead.status == "accepted")
        elif segment == "not_accepted":
            q = q.where(Lead.status != "accepted")
        return list((await s.execute(q)).scalars().all())


async def send_one(tg_id: int, kind: str, text: str, file_path: str | None, file_id_cache: dict) -> None:
    from ..bot.instance import get_bot

    bot = get_bot()
    if kind == "text" or not file_path:
        await bot.send_message(tg_id, text, disable_web_page_preview=True)
        return
    media = file_id_cache.get("id") or FSInputFile(Path(file_path))
    if kind == "photo":
        m = await bot.send_photo(tg_id, media, caption=text)
        file_id_cache.setdefault("id", m.photo[-1].file_id if m.photo else None)
    else:
        m = await bot.send_video(tg_id, media, caption=text)
        file_id_cache.setdefault("id", m.video.file_id if m.video else None)


async def _run(bid: int) -> None:
    async with session_scope() as s:
        b = await s.get(Broadcast, bid)
        segment, kind, text, file_path = b.segment, b.kind, b.text, b.file_path
    ids = await recipients(segment)
    async with session_scope() as s:
        b = await s.get(Broadcast, bid)
        b.status, b.total, b.started_at = "running", len(ids), utcnow()
    sent = failed = blocked = 0
    cache: dict = {}
    for i, tg_id in enumerate(ids):
        async with session_scope() as s:
            if (await s.get(Broadcast, bid)).status == "cancelled":
                break
        for _attempt in range(3):
            try:
                await send_one(tg_id, kind, text, file_path, cache)
                sent += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                blocked += 1
                async with session_scope() as s:
                    lead = (await s.execute(select(Lead).where(Lead.tg_id == tg_id))).scalars().first()
                    if lead:
                        lead.is_blocked = True
                break
            except Exception as e:  # noqa: BLE001
                log.warning("Broadcast xato %s: %s", tg_id, e)
                failed += 1
                break
        await asyncio.sleep(0.05)  # ~20 xabar/soniya
        if i % 20 == 0:
            async with session_scope() as s:
                b = await s.get(Broadcast, bid)
                b.sent, b.failed, b.blocked = sent, failed, blocked
            await hub.emit("broadcast", {"id": bid, "sent": sent, "failed": failed, "blocked": blocked, "total": len(ids)},
                           admins_only=True)
    async with session_scope() as s:
        b = await s.get(Broadcast, bid)
        b.sent, b.failed, b.blocked = sent, failed, blocked
        if b.status != "cancelled":
            b.status = "done"
        b.finished_at = utcnow()
    await hub.emit("broadcast", {"id": bid, "sent": sent, "failed": failed, "blocked": blocked, "total": len(ids),
                                 "done": True}, admins_only=True)
    _running.pop(bid, None)


def start(bid: int) -> None:
    _running[bid] = asyncio.create_task(_run(bid))
