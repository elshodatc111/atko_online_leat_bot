"""Panel orqali tahrirlanadigan sozlamalar (bazada saqlanadi, xotirada keshlanadi)."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select

from ..db import session_scope
from ..models import Setting

DEFAULTS: dict[str, Any] = {
    # Ish vaqti
    "work_start": "08:00",
    "work_end": "20:00",
    "days_off": [6],  # 0=Dushanba ... 6=Yakshanba
    # Operator chat
    "max_chats_per_operator": 5,
    "sla_wait_minutes": 10,  # shu vaqtda hech kim chatni olmasa — adminga xabar
    "idle_reply_minutes": 5,  # faol chatda operator javob bermasa — ogohlantirish
    "sla_notify_lead": True,
    # Fayl hajmi cheklovlari (MB)
    "max_photo_mb": 10,
    "max_audio_mb": 20,
    "max_video_mb": 20,
    "max_document_mb": 20,
    # AI
    "ai_enabled": True,
    "openai_api_key": "",  # bo'sh bo'lsa .env dagi OPENAI_API_KEY ishlatiladi
    "ai_model": "gpt-5.4-mini",
    "ai_transcribe_model": "gpt-4o-mini-transcribe",
    "ai_embedding_model": "text-embedding-3-small",
    "ai_reasoning_effort": "low",
    "ai_daily_token_limit": 1_000_000,
    "ai_price_input_per_1m": 0.0,
    "ai_price_output_per_1m": 0.0,
    "ai_history_messages": 12,
    "ai_transcribe_voice": True,
    "ai_auto_escalate": True,
    "ai_extra_instructions": "",
    # Tutor
    "tutor_enabled": True,
    "tutor_trial_daily": 5,  # kursga qabul qilinmaganlar uchun kunlik bepul savollar
    # FAQ tahlili
    "faq_auto_enabled": True,
    "faq_auto_hour": 3,
    "faq_min_count": 3,
    "faq_last_run": None,
    # Eslatmalar
    "reminders_enabled": True,
    "reminder_hours_from": "10:00",
    "reminder_hours_to": "19:00",
    # Bot matnlari (override) — {key: {"uz": ..., "ru": ...}}
    "texts": {},
}

_cache: dict[str, Any] | None = None


async def load() -> dict[str, Any]:
    global _cache
    async with session_scope() as s:
        rows = (await s.execute(select(Setting))).scalars().all()
    data = copy.deepcopy(DEFAULTS)
    for r in rows:
        data[r.key] = r.value
    _cache = data
    return data


async def all_settings() -> dict[str, Any]:
    if _cache is None:
        return await load()
    return _cache


async def get(key: str, default: Any = None) -> Any:
    data = await all_settings()
    if key in data:
        return data[key]
    return DEFAULTS.get(key, default)


async def set_many(values: dict[str, Any]) -> None:
    async with session_scope() as s:
        for k, v in values.items():
            row = await s.get(Setting, k)
            if row is None:
                s.add(Setting(key=k, value=v))
            else:
                row.value = v
    await load()


async def set_value(key: str, value: Any) -> None:
    await set_many({key: value})
