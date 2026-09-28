"""Real vaqt bildirishnomalari: veb-panel (WebSocket) va xodimlarning Telegrami."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import WebSocket
from sqlalchemy import select

from ..config import config
from ..db import session_scope
from ..models import Staff

log = logging.getLogger(__name__)


class Hub:
    def __init__(self) -> None:
        self.conns: dict[int, set[WebSocket]] = defaultdict(set)
        self.roles: dict[int, str] = {}

    async def connect(self, staff_id: int, role: str, ws: WebSocket) -> None:
        await ws.accept()
        self.conns[staff_id].add(ws)
        self.roles[staff_id] = role

    def disconnect(self, staff_id: int, ws: WebSocket) -> None:
        self.conns[staff_id].discard(ws)
        if not self.conns[staff_id]:
            self.conns.pop(staff_id, None)

    def online_ids(self) -> set[int]:
        return set(self.conns.keys())

    async def _send(self, ws: WebSocket, payload: str) -> bool:
        try:
            await ws.send_text(payload)
            return True
        except Exception:
            return False

    async def emit(self, event: str, data: dict[str, Any] | None = None, staff_ids: set[int] | None = None,
                   admins_only: bool = False) -> None:
        payload = json.dumps({"event": event, "data": data or {}}, default=str, ensure_ascii=False)
        tasks = []
        targets = []
        for sid, sockets in list(self.conns.items()):
            if staff_ids is not None and sid not in staff_ids:
                continue
            if admins_only and self.roles.get(sid) != "admin":
                continue
            for ws in list(sockets):
                targets.append((sid, ws))
                tasks.append(self._send(ws, payload))
        if not tasks:
            return
        results = await asyncio.gather(*tasks)
        for (sid, ws), ok in zip(targets, results):
            if not ok:
                self.disconnect(sid, ws)


hub = Hub()


def _panel_kb(path: str, label: str = "🖥 Panelda ochish") -> InlineKeyboardMarkup | None:
    url = f"{config.PANEL_URL}{path}"
    # Telegram localhost havolalarini tugma sifatida qabul qilmaydi
    if "localhost" in url or "127.0.0.1" in url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])


async def telegram_staff(text: str, *, staff_ids: list[int] | None = None, admins: bool = False,
                         online_operators: bool = False, path: str | None = None) -> None:
    """Xodimlarning shaxsiy Telegramiga xabar yuborish."""
    from ..bot.instance import get_bot

    async with session_scope() as s:
        q = select(Staff).where(Staff.is_active.is_(True), Staff.tg_id.is_not(None))
        rows = (await s.execute(q)).scalars().all()
    targets: dict[int, Staff] = {}
    for st in rows:
        if staff_ids is not None and st.id in staff_ids:
            targets[st.id] = st
        if admins and st.role == "admin":
            targets[st.id] = st
        if online_operators and st.role == "operator" and st.is_online:
            targets[st.id] = st
    if online_operators and not any(t.role == "operator" for t in targets.values()):
        # onlayn operator yo'q — barcha faol operatorlar va adminga
        for st in rows:
            targets[st.id] = st
    if not targets:
        return
    bot = get_bot()
    kb = _panel_kb(path) if path else None
    if path and kb is None:
        text = f"{text}\n\n🖥 {config.PANEL_URL}{path}"
    for st in targets.values():
        try:
            await bot.send_message(st.tg_id, text, reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:  # noqa: BLE001
            log.warning("Xodimga xabar yuborilmadi %s: %s", st.id, e)
