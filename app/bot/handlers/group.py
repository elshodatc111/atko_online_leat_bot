"""Premium guruh: qo'shilish so'rovlari, a'zolar nazorati va bot qo'shilgan chatlarni aniqlash (sozlamalarda tanlash uchun)."""
from __future__ import annotations

import html
import logging

from aiogram import Router
from aiogram.types import ChatJoinRequest, ChatMemberUpdated

from ...services import settings, subscriptions
from ...services.notify import telegram_staff

log = logging.getLogger(__name__)
router = Router(name="group")

STATUS_UZ = {"administrator": "admin", "member": "a'zo", "left": "chiqarildi", "kicked": "chiqarildi", "restricted": "cheklangan"}


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
    """Bot guruhga qo'shilsa yoki admin qilinsa — chat sozlamalarda «Premium guruh» sifatida tanlash uchun saqlanadi."""
    if upd.chat.type not in ("group", "supergroup", "channel"):
        return
    status = upd.new_chat_member.status
    status = status if isinstance(status, str) else status.value
    known = dict(await settings.get("known_chats") or {})
    if status in ("left", "kicked"):
        known.pop(str(upd.chat.id), None)
    else:
        known[str(upd.chat.id)] = {"title": upd.chat.title or "", "status": status, "type": upd.chat.type}
    await settings.set_value("known_chats", known)
    is_premium = str(await settings.get("group_chat_id") or "") == str(upd.chat.id)
    if is_premium:
        note = "\n\n💎 Bu — Premium guruh."
    elif status == "administrator" and upd.chat.type != "channel":
        note = "\n\n⚙️ Premium guruh sifatida ulash: panel → Sozlamalar → «Premium guruh»."
    else:
        note = ""
    await telegram_staff(
        f"🤖 Botning chatdagi holati o'zgardi\n📛 {html.escape(upd.chat.title or '')}\n🆔 <code>{upd.chat.id}</code>\n"
        f"📌 Holat: <b>{STATUS_UZ.get(status, status)}</b>{note}",
        admins=True, path="/settings#group",
    )
