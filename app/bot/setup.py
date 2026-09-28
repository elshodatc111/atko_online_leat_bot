"""Dispatcher va botni ishga tushirish (polling yoki webhook)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Dispatcher
from aiogram.types import BotCommand

from ..config import config
from .handlers import menu, messages, start
from .instance import get_bot
from .middlewares import LeadHistoryMiddleware

log = logging.getLogger(__name__)

dp = Dispatcher()
_history = LeadHistoryMiddleware()
dp.message.outer_middleware(_history)
dp.callback_query.outer_middleware(_history)
dp.include_router(start.router)
dp.include_router(menu.router)
dp.include_router(messages.router)

_polling_task: asyncio.Task | None = None


def webhook_path() -> str:
    return f"/tg/webhook/{config.WEBHOOK_SECRET}"


async def start_bot() -> None:
    global _polling_task
    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN yo'q — bot ishga tushmadi (panel ishlaydi)")
        return
    try:
        await _start()
    except Exception as e:  # noqa: BLE001
        log.error("Botni ishga tushirib bo'lmadi (token yoki internetni tekshiring): %s", e)


async def _start() -> None:
    global _polling_task
    bot = get_bot()
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Boshlash / Начать")])
    except Exception as e:  # noqa: BLE001
        log.warning("Buyruqlarni o'rnatib bo'lmadi: %s", e)
    if config.BOT_MODE == "webhook":
        if not config.WEBHOOK_BASE_URL:
            log.error("WEBHOOK_BASE_URL ko'rsatilmagan")
            return
        url = config.WEBHOOK_BASE_URL + webhook_path()
        await bot.set_webhook(url, drop_pending_updates=False, allowed_updates=dp.resolve_used_update_types())
        log.info("Webhook o'rnatildi: %s", config.WEBHOOK_BASE_URL + "/tg/webhook/***")
    else:
        await bot.delete_webhook(drop_pending_updates=False)
        _polling_task = asyncio.create_task(
            dp.start_polling(bot, handle_signals=False, allowed_updates=dp.resolve_used_update_types())
        )
        log.info("Bot polling rejimida ishga tushdi")


async def stop_bot() -> None:
    global _polling_task
    if _polling_task:
        try:
            await dp.stop_polling()
        except Exception:  # noqa: BLE001
            pass
        _polling_task.cancel()
        try:
            await _polling_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _polling_task = None
    if config.BOT_TOKEN:
        await get_bot().session.close()
