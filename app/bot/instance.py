"""Yagona Bot obyekti."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

from ..config import config

log = logging.getLogger(__name__)
_bot: Bot | None = None


class SafeHtmlMiddleware(BaseRequestMiddleware):
    """Matnda noto'g'ri HTML bo'lsa (Telegram «can't parse entities» xatosi) — xabar oddiy matn sifatida qayta yuboriladi.
    Shu tufayli bitta noto'g'ri teg botni «jim» qilib qo'ymaydi."""

    async def __call__(self, make_request, bot, method):
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as e:
            if "can't parse entities" not in str(e).lower():
                raise
            from .tghtml import to_plain

            upd: dict = {"parse_mode": None}
            for field in ("text", "caption"):
                val = getattr(method, field, None)
                if isinstance(val, str):
                    upd[field] = to_plain(val)
            if len(upd) == 1 or not hasattr(method, "parse_mode"):
                raise
            log.warning("HTML xato (%s) — xabar oddiy matn sifatida yuborildi: %s", type(method).__name__, e)
            return await make_request(bot, method.model_copy(update=upd))
_username: str | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        if not config.BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan")
        _bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        _bot.session.middleware(SafeHtmlMiddleware())
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
