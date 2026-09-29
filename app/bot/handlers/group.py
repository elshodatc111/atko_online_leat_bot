"""Guruh va kanallar: Premium guruh (qo'shilish so'rovlari, a'zolar nazorati), o'quv guruhlari (a'zolar soni),
asosiy kanal (postlar, reaksiyalar, obunachilar) va bot qo'shilgan chatlarni aniqlash."""
from __future__ import annotations

import html
import logging

from aiogram import Router
from aiogram.types import ChatJoinRequest, ChatMemberUpdated, Message, MessageReactionCountUpdated

from ...services import channel, settings, subscriptions, tgchats
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
    try:
        await tgchats.on_member_update(upd)
    except Exception:  # noqa: BLE001
        log.exception("A'zolar statistikasini yozishda xato")


@router.channel_post()
async def channel_post(msg: Message) -> None:
    try:
        await channel.on_post(msg)
    except Exception:  # noqa: BLE001
        log.exception("Kanal postini yozishda xato")


@router.edited_channel_post()
async def channel_post_edited(msg: Message) -> None:
    try:
        await channel.on_post(msg, edited=True)
    except Exception:  # noqa: BLE001
        log.exception("Kanal postini yangilashda xato")


@router.message_reaction_count()
async def reactions(upd: MessageReactionCountUpdated) -> None:
    try:
        await channel.on_reactions(upd)
    except Exception:  # noqa: BLE001
        log.exception("Reaksiyalarni yozishda xato")


@router.my_chat_member()
async def bot_status(upd: ChatMemberUpdated) -> None:
    """Bot guruhga qo'shilsa yoki admin qilinsa — guruh ID si panelda tanlash uchun saqlanadi."""
    if upd.chat.type not in ("group", "supergroup", "channel"):
        return
    status = upd.new_chat_member.status
    status = status if isinstance(status, str) else status.value
    try:
        x = await tgchats.on_bot_status(upd)
    except Exception:  # noqa: BLE001
        log.exception("Chatni ro'yxatga yozishda xato")
        x = None
    known = dict(await settings.get("known_chats") or {})
    known[str(upd.chat.id)] = {"title": upd.chat.title or "", "status": status, "type": upd.chat.type}
    await settings.set_value("known_chats", known)
    from ...models import CHAT_ROLES

    role = x.role if x else "unassigned"
    note, path = "", "/groups"
    if role == "study":
        note = "\n\n👥 O'quv guruhi sifatida qo'shildi: panel → «O'quv guruhlari» (post yuborish, o'quvchilar soni)."
    elif role == "channel":
        note, path = "\n\n📈 Asosiy kanal: panel → «Kanal rivoji» (tahlil va kunlik AI g'oyalar).", "/channel"
    elif role == "premium":
        path = "/settings#group"
    elif status == "administrator":
        note = "\n\n⚙️ Panel → «O'quv guruhlari» → «Boshqa chatlar» bo'limida bu chat vazifasini tanlang."
    await telegram_staff(
        f"🤖 Botning chatdagi holati o'zgardi\n📛 {html.escape(upd.chat.title or '')}\n🆔 <code>{upd.chat.id}</code>\n"
        f"📌 Holat: <b>{status}</b> · {CHAT_ROLES.get(role, role)}{note}",
        admins=True, path=path,
    )
