"""Yopiq Telegram guruh: qo'shilish so'rovlari, a'zolar nazorati, bot qo'shilgan guruhlarni aniqlash."""
from __future__ import annotations

import html
import logging

from aiogram import Router
from aiogram.types import ChatJoinRequest, ChatMemberUpdated

from ...services import settings, subscriptions
from ...services.notify import telegram_staff

log = logging.getLogger(__name__)
router = Router(name="group")


@router.chat_join_request()
async def join_request(req: ChatJoinRequest) -> None:
    try:
        await subscriptions.handle_join_request(req)
    except Exception:  # noqa: BLE001
        log.exception("Qo'shilish so'rovini qayta ishlashda xato")


@router.chat_member()
async def member_update(upd: ChatMemberUpdated) -> None:
    try:
        await subscriptions.handle_member_update(upd)
    except Exception:  # noqa: BLE001
        log.exception("A'zo holatini qayta ishlashda xato")


@router.my_chat_member()
async def bot_status(upd: ChatMemberUpdated) -> None:
    """Bot guruhga qo'shilsa yoki admin qilinsa — guruh ID si panelda tanlash uchun saqlanadi."""
    if upd.chat.type not in ("group", "supergroup", "channel"):
        return
    status = upd.new_chat_member.status
    status = status if isinstance(status, str) else status.value
    known = dict(await settings.get("known_chats") or {})
    known[str(upd.chat.id)] = {"title": upd.chat.title or "", "status": status, "type": upd.chat.type}
    await settings.set_value("known_chats", known)
    gid = await subscriptions.group_id()
    note = ""
    if not gid and status == "administrator":
        note = "\n\n⚙️ Panel → Sozlamalar → «Yopiq guruh» bo'limida shu guruhni tanlang."
    await telegram_staff(
        f"🤖 Botning guruhdagi holati o'zgardi\n📛 {html.escape(upd.chat.title or '')}\n🆔 <code>{upd.chat.id}</code>\n📌 Holat: <b>{status}</b>{note}",
        admins=True, path="/settings#group",
    )
