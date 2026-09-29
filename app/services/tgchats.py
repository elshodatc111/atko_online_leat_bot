"""Bot qo'shilgan Telegram chatlar: asosiy kanal, o'quv guruhlari, Premium guruh.

- Bot guruh/kanalga qo'shilganda yoki huquqlari o'zgarganda — ro'yxatga yoziladi.
- A'zolar soni Telegram'dan olinadi, har kuni tarixga yoziladi; qo'shilgan/chiqib ketganlar hisoblanadi.
- Admin paneldan chatni o'chirsa — bot chatdan chiqadi.
"""
from __future__ import annotations

import logging
import time
from datetime import date

from sqlalchemy import select

from ..db import session_scope, utcnow
from ..models import ChannelInvite, ChatStat, TgChat
from . import settings, worktime

log = logging.getLogger(__name__)

MEMBER_STATES = {"member", "administrator", "creator", "restricted"}
_last_count: dict[int, float] = {}


def _status(member) -> str:
    st = member.status
    return st if isinstance(st, str) else st.value


def is_member(member) -> bool:
    st = _status(member)
    if st == "restricted":
        return bool(getattr(member, "is_member", True))
    return st in MEMBER_STATES


def today() -> date:
    return worktime.now_local().date()


async def channel_username() -> str:
    return str(await settings.get("channel_username") or "").lstrip("@").lower()


async def get(chat_id: int) -> TgChat | None:
    async with session_scope() as s:
        return (await s.execute(select(TgChat).where(TgChat.chat_id == chat_id))).scalars().first()


async def list_chats(role: str | None = None, active_only: bool = True) -> list[TgChat]:
    async with session_scope() as s:
        q = select(TgChat)
        if role:
            q = q.where(TgChat.role == role)
        if active_only:
            q = q.where(TgChat.is_active.is_(True), TgChat.removed_at.is_(None))
        return list((await s.execute(q.order_by(TgChat.title))).scalars().all())


async def main_channel() -> TgChat | None:
    async with session_scope() as s:
        return (await s.execute(select(TgChat).where(TgChat.role == "channel", TgChat.removed_at.is_(None))
                                .order_by(TgChat.is_active.desc(), TgChat.id.desc()))).scalars().first()


async def _auto_role(chat, existing_role: str | None) -> str:
    """Yangi chat uchun rol: Premium guruh → premium, @atko_teams → channel, guruhlar → study."""
    if existing_role and existing_role != "unassigned":
        return existing_role
    from . import subscriptions

    if await subscriptions.group_id() == chat.id:
        return "premium"
    if chat.type == "channel":
        uname = (chat.username or "").lower()
        if uname and uname == await channel_username():
            return "channel"
        return "unassigned"
    return "study"


async def on_bot_status(upd) -> TgChat:
    """my_chat_member: bot qo'shildi / admin qilindi / chiqarildi."""
    chat = upd.chat
    nm = upd.new_chat_member
    status = _status(nm)
    active = status in ("member", "administrator", "creator") or (status == "restricted" and getattr(nm, "is_member", False))
    async with session_scope() as s:
        x = (await s.execute(select(TgChat).where(TgChat.chat_id == chat.id))).scalars().first()
        if x is None:
            x = TgChat(chat_id=chat.id, type=chat.type)
            s.add(x)
        x.type = chat.type
        x.title = chat.title or x.title or ""
        x.username = chat.username or x.username
        x.bot_status = status
        x.can_post = bool(getattr(nm, "can_post_messages", False)) or (status == "administrator" and chat.type != "channel")
        x.can_invite = bool(getattr(nm, "can_invite_users", False))
        x.can_pin = bool(getattr(nm, "can_pin_messages", False))
        x.can_delete = bool(getattr(nm, "can_delete_messages", False))
        if active:
            if not x.is_active or x.removed_at:
                x.added_at = utcnow()
            x.is_active, x.left_at, x.removed_at = True, None, None
        else:
            x.is_active, x.left_at = False, utcnow()
        x.role = await _auto_role(chat, x.role)
        role = x.role
    if role == "channel":
        await settings.set_value("channel_chat_id", chat.id)
    if active:
        await refresh(chat.id)
    return await get(chat.id)


async def refresh(chat_id: int) -> TgChat | None:
    """A'zolar soni, adminlar va nomni Telegram'dan yangilaydi (bugungi statistikaga ham yoziladi)."""
    from ..bot.instance import get_bot

    bot = get_bot()
    try:
        info = await bot.get_chat(chat_id)
        count = await bot.get_chat_member_count(chat_id)
        try:
            admins = len(await bot.get_chat_administrators(chat_id))
        except Exception:  # noqa: BLE001
            admins = 0
    except Exception as e:  # noqa: BLE001
        log.warning("Chat ma'lumotini olib bo'lmadi %s: %s", chat_id, e)
        return await get(chat_id)
    _last_count[chat_id] = time.monotonic()
    async with session_scope() as s:
        x = (await s.execute(select(TgChat).where(TgChat.chat_id == chat_id))).scalars().first()
        if x is None:
            return None
        x.title = info.title or x.title
        x.username = info.username or x.username
        x.members, x.admins, x.members_updated_at = count, admins, utcnow()
        await _stat_row(s, chat_id, members=count)
    return await get(chat_id)


async def _stat_row(s, chat_id: int, members: int | None = None, joined: int = 0, left: int = 0) -> ChatStat:
    d = today()
    row = (await s.execute(select(ChatStat).where(ChatStat.chat_id == chat_id, ChatStat.day == d))).scalars().first()
    if row is None:
        prev = (await s.execute(select(ChatStat).where(ChatStat.chat_id == chat_id).order_by(ChatStat.day.desc()))).scalars().first()
        row = ChatStat(chat_id=chat_id, day=d, members=prev.members if prev else 0, joined=0, left=0)
        s.add(row)
    if members is not None:
        row.members = members
    row.joined = (row.joined or 0) + joined
    row.left = (row.left or 0) + left
    return row


async def on_member_update(upd) -> None:
    """chat_member: a'zo qo'shildi / chiqib ketdi — kunlik hisob, taklif havolasi hisobi, sonni yangilash."""
    was, now = is_member(upd.old_chat_member), is_member(upd.new_chat_member)
    if was == now:
        return
    chat_id = upd.chat.id
    if await get(chat_id) is None:
        return
    link = getattr(upd.invite_link, "invite_link", None) if upd.invite_link else None
    async with session_scope() as s:
        await _stat_row(s, chat_id, joined=1 if now else 0, left=0 if now else 1)
        x = (await s.execute(select(TgChat).where(TgChat.chat_id == chat_id))).scalars().first()
        if x:
            x.members = max(0, (x.members or 0) + (1 if now else -1))
            (await _stat_row(s, chat_id)).members = x.members
        if link and now:
            inv = (await s.execute(select(ChannelInvite).where(ChannelInvite.link == link))).scalars().first()
            if inv:
                inv.joins = (inv.joins or 0) + 1
    # vaqti-vaqti bilan Telegram'dagi aniq son bilan tekislaymiz
    if time.monotonic() - _last_count.get(chat_id, 0) > 600:
        await refresh(chat_id)


async def snapshot_all() -> int:
    """Fon vazifasi: barcha faol chatlar a'zolar sonini yangilaydi (kunlik tarix)."""
    n = 0
    for c in await list_chats():
        if await refresh(c.chat_id):
            n += 1
    return n


async def set_role(chat_id: int, role: str) -> None:
    async with session_scope() as s:
        x = (await s.execute(select(TgChat).where(TgChat.chat_id == chat_id))).scalars().first()
        if not x:
            return
        if role == "channel":
            # asosiy kanal bitta bo'ladi
            for other in (await s.execute(select(TgChat).where(TgChat.role == "channel", TgChat.chat_id != chat_id))).scalars().all():
                other.role = "unassigned"
        x.role = role
        uname = x.username
    if role == "channel":
        await settings.set_many({"channel_chat_id": chat_id, "channel_username": (uname or "").lower()})


async def remove(chat_id: int) -> bool:
    """Admin chatni ro'yxatdan o'chiradi — bot chatdan chiqadi (tarix saqlanadi)."""
    from ..bot.instance import get_bot

    ok = True
    try:
        await get_bot().leave_chat(chat_id)
    except Exception as e:  # noqa: BLE001
        log.warning("Chatdan chiqib bo'lmadi %s: %s", chat_id, e)
        ok = False
    async with session_scope() as s:
        x = (await s.execute(select(TgChat).where(TgChat.chat_id == chat_id))).scalars().first()
        if x:
            x.is_active, x.removed_at, x.left_at = False, utcnow(), utcnow()
    return ok


async def history(chat_ids: list[int], days: int = 30) -> dict[int, list[ChatStat]]:
    from datetime import timedelta

    since = today() - timedelta(days=days - 1)
    async with session_scope() as s:
        rows = (await s.execute(select(ChatStat).where(ChatStat.chat_id.in_(chat_ids or [0]), ChatStat.day >= since)
                                .order_by(ChatStat.day))).scalars().all()
    out: dict[int, list[ChatStat]] = {cid: [] for cid in chat_ids}
    for r in rows:
        out.setdefault(r.chat_id, []).append(r)
    return out


async def change_since(chat_id: int, days: int) -> int | None:
    """Oxirgi N kunda a'zolar soni o'zgarishi."""
    from datetime import timedelta

    async with session_scope() as s:
        base = (await s.execute(select(ChatStat).where(ChatStat.chat_id == chat_id, ChatStat.day <= today() - timedelta(days=days))
                                .order_by(ChatStat.day.desc()))).scalars().first()
        first = base or (await s.execute(select(ChatStat).where(ChatStat.chat_id == chat_id).order_by(ChatStat.day))).scalars().first()
        cur = await s.execute(select(TgChat.members).where(TgChat.chat_id == chat_id))
        members = cur.scalar_one_or_none()
    if not first or members is None:
        return None
    return members - first.members


async def register(ref: int | str) -> TgChat | None:
    """Bot allaqachon a'zo bo'lgan chatni qo'lda ro'yxatga oladi (@username yoki ID bo'yicha)."""
    from types import SimpleNamespace

    from ..bot.instance import get_bot

    bot = get_bot()
    chat = await bot.get_chat(ref)
    me = await bot.get_me()
    member = await bot.get_chat_member(chat.id, me.id)
    return await on_bot_status(SimpleNamespace(chat=chat, new_chat_member=member))


async def bootstrap() -> None:
    """Birinchi ishga tushishda: oldin ma'lum bo'lgan guruhlar (known_chats) va asosiy kanalni ro'yxatga oladi."""
    if await settings.get("tgchats_bootstrapped"):
        return
    refs: list[int | str] = []
    for cid in (await settings.get("known_chats") or {}):
        if str(cid).lstrip("-").isdigit():
            refs.append(int(cid))
    uname = await channel_username()
    if uname:
        refs.append("@" + uname)
    for ref in refs:
        try:
            await register(ref)
        except Exception as e:  # noqa: BLE001
            log.info("Chatni ro'yxatga olib bo'lmadi %s: %s", ref, e)
    await settings.set_value("tgchats_bootstrapped", True)
