"""Yagona Bot obyekti."""
from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from ..config import config

_bot: Bot | None = None
_username: str | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        if not config.BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan")
        _bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _bot


async def bot_username() -> str:
    global _username
    if _username is None:
        try:
            me = await get_bot().get_me()
            _username = me.username or "bot"
        except Exception:
            return "bot"
    return _username


def deep_link(username: str, payload: str) -> str:
    return f"https://t.me/{username}?start={payload}"
