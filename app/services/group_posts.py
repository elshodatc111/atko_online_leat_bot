"""O'quv guruhlariga va asosiy kanalga post yuborish: matn / matn+rasm / matn+video, darhol yoki rejalashtirilgan, qadash (pin) bilan."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram.types import FSInputFile
from sqlalchemy import select

from ..db import session_scope, utcnow
from ..models import GroupPost, GroupPostDelivery, TgChat
from .notify import hub

log = logging.getLogger(__name__)

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
_lock = asyncio.Lock()


def validate(kind: str, text: str) -> str | None:
    if kind == "text" and not text.strip():
        return "Matn bo'sh"
    limit = TEXT_LIMIT if kind == "text" else CAPTION_LIMIT
    if len(text) > limit:
        return f"Matn juda uzun: {len(text)} belgi (ruxsat: {limit}). Rasm/video bilan izoh 1024 belgigacha bo'ladi."
    return None


async def _send_one(bot, post: GroupPost, chat_id: int, media) -> tuple[int | None, str | None, str | None]:
    """(message_id, xato, yangi file_id)"""
    kw = {"disable_notification": post.silent}
    text = post.text or None
    try:
        if post.kind == "photo":
            m = await bot.send_photo(chat_id, media, caption=text, **kw)
            fid = m.photo[-1].file_id if m.photo else None
        elif post.kind == "video":
            m = await bot.send_video(chat_id, media, caption=text, supports_streaming=True, **kw)
            fid = m.video.file_id if m.video else None
        else:
            m = await bot.send_message(chat_id, post.text, disable_web_page_preview=False, **kw)
            fid = None
    except Exception as e:  # noqa: BLE001
        # HTML xato bo'lsa — oddiy matn sifatida qayta urinamiz
        if "parse" in str(e).lower() or "entities" in str(e).lower():
            kw["parse_mode"] = None
            try:
                if post.kind == "photo":
                    m = await bot.send_photo(chat_id, media, caption=text, **kw)
                    fid = m.photo[-1].file_id if m.photo else None
                elif post.kind == "video":
                    m = await bot.send_video(chat_id, media, caption=text, **kw)
                    fid = m.video.file_id if m.video else None
                else:
                    m = await bot.send_message(chat_id, post.text, **kw)
                    fid = None
            except Exception as e2:  # noqa: BLE001
                return None, str(e2)[:500], None
        else:
            return None, str(e)[:500], None
    if post.pin:
        try:
            await bot.pin_chat_message(chat_id, m.message_id, disable_notification=post.silent)
        except Exception as e:  # noqa: BLE001
            log.warning("Qadab bo'lmadi %s: %s", chat_id, e)
    return m.message_id, None, fid


async def send(post_id: int) -> GroupPost | None:
    """Postni barcha tanlangan guruhlarga yuboradi (bir marta)."""
    from ..bot.instance import get_bot

    async with _lock:
        async with session_scope() as s:
            post = await s.get(GroupPost, post_id)
            if not post or post.status not in ("scheduled",):
                return post
            post.status = "sending"
            targets = list(post.targets or [])
            chats = {c.chat_id: c for c in (await s.execute(select(TgChat).where(TgChat.chat_id.in_(targets or [0])))).scalars().all()}
        await hub.emit("group_post", {"id": post_id, "status": "sending"})
        bot = get_bot()
        async with session_scope() as s:
            post = await s.get(GroupPost, post_id)
        media = post.file_id or (FSInputFile(post.file_path, filename=post.file_name) if post.file_path else None)
        ok = fail = 0
        for cid in targets:
            c = chats.get(cid)
            if c is None or not c.is_active or c.removed_at:
                mid, err, fid = None, "Bot bu guruhda emas", None
            else:
                mid, err, fid = await _send_one(bot, post, cid, media)
                if fid and not post.file_id:
                    # keyingi guruhlarga fayl Telegram bulutidan yuboriladi (serverdan qayta yuklanmaydi)
                    post.file_id = fid
                    media = fid
                    async with session_scope() as s:
                        (await s.get(GroupPost, post_id)).file_id = fid
            async with session_scope() as s:
                s.add(GroupPostDelivery(post_id=post_id, chat_id=cid, title=c.title if c else str(cid), message_id=mid,
                                        ok=mid is not None, error=err))
                if mid and post.dest == "channel":
                    # bot o'z postlari haqida update olmaydi — kanal tahlili uchun o'zimiz yozib qo'yamiz
                    from ..models import ChannelPost

                    s.add(ChannelPost(chat_id=cid, message_id=mid, posted_at=utcnow(), kind=post.kind, text=post.text or "",
                                      subscribers_at_post=c.members if c else None, source="live"))
            ok += mid is not None
            fail += mid is None
            await asyncio.sleep(0.05)
        async with session_scope() as s:
            post = await s.get(GroupPost, post_id)
            post.status = "sent" if ok and not fail else ("partial" if ok else "failed")
            post.sent_at = utcnow()
            if post.file_id and post.file_path:
                Path(post.file_path).unlink(missing_ok=True)
                post.file_path = None
            status = post.status
        await hub.emit("group_post", {"id": post_id, "status": status})
        return post


async def send_test(post_id: int, tg_id: int) -> str | None:
    """Postni adminga (shaxsiy chatga) sinov uchun yuboradi. Xato bo'lsa matnini qaytaradi."""
    from ..bot.instance import get_bot

    async with session_scope() as s:
        post = await s.get(GroupPost, post_id)
    if not post:
        return "Post topilmadi"
    media = post.file_id or (FSInputFile(post.file_path, filename=post.file_name) if post.file_path else None)
    test = GroupPost(kind=post.kind, text=post.text, pin=False, silent=False)
    mid, err, fid = await _send_one(get_bot(), test, tg_id, media)
    if fid and not post.file_id:
        async with session_scope() as s:
            p = await s.get(GroupPost, post_id)
            p.file_id = fid
    return err


async def delete_from_groups(post_id: int) -> tuple[int, int]:
    """Yuborilgan postni guruhlardan o'chiradi (Telegram 48 soatdan eski xabarlarni o'chirishga ruxsat bermasligi mumkin)."""
    from ..bot.instance import get_bot

    bot = get_bot()
    async with session_scope() as s:
        post = await s.get(GroupPost, post_id)
        items = [d for d in (post.deliveries if post else []) if d.ok and not d.deleted and d.message_id]
    ok = fail = 0
    for d in items:
        try:
            await bot.delete_message(d.chat_id, d.message_id)
            ok += 1
            async with session_scope() as s:
                x = await s.get(GroupPostDelivery, d.id)
                x.deleted = True
        except Exception as e:  # noqa: BLE001
            fail += 1
            async with session_scope() as s:
                x = await s.get(GroupPostDelivery, d.id)
                x.error = f"O'chirib bo'lmadi: {e}"[:500]
    if ok:
        async with session_scope() as s:
            p = await s.get(GroupPost, post_id)
            if not fail:
                p.status = "deleted"
    return ok, fail


async def due_job() -> None:
    """Fon vazifasi: vaqti kelgan rejalashtirilgan postlarni yuboradi."""
    async with session_scope() as s:
        ids = (await s.execute(select(GroupPost.id).where(GroupPost.status == "scheduled", GroupPost.scheduled_at <= utcnow())
                               .order_by(GroupPost.scheduled_at))).scalars().all()
    for pid in ids:
        try:
            await send(pid)
        except Exception:  # noqa: BLE001
            log.exception("Rejalashtirilgan postni yuborishda xato")
            async with session_scope() as s:
                p = await s.get(GroupPost, pid)
                if p and p.status == "sending":
                    p.status, p.error = "failed", "Kutilmagan xato — jurnalga qarang"
