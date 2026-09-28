"""Loyiha sozlamalari (.env faylidan o'qiladi)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "ha", "on"}


def _ids(name: str) -> list[int]:
    raw = os.getenv(name, "")
    out: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
    # polling — lokal kompyuter uchun, webhook — server (alwaysdata) uchun
    BOT_MODE: str = (os.getenv("BOT_MODE") or "polling").strip().lower()
    WEBHOOK_BASE_URL: str = os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "").strip() or secrets.token_hex(16)

    ADMIN_TG_IDS: list[int] = _ids("ADMIN_TG_IDS")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()

    PAYME_MERCHANT_ID: str = os.getenv("PAYME_MERCHANT_ID", "").strip()
    PAYME_KEY: str = os.getenv("PAYME_KEY", "").strip()
    PAYME_TEST_KEY: str = os.getenv("PAYME_TEST_KEY", "").strip()

    SECRET_KEY: str = os.getenv("SECRET_KEY", "").strip() or "change-me-" + secrets.token_hex(8)
    PANEL_URL: str = (os.getenv("PANEL_URL") or "http://localhost:8000").strip().rstrip("/")

    # alwaysdata $IP va $PORT o'zgaruvchilarini beradi — ular ustun turadi
    HOST: str = os.getenv("IP") or os.getenv("HOST") or "127.0.0.1"
    PORT: int = int(os.getenv("PORT") or "8000")

    DATA_DIR: Path = Path(os.getenv("DATA_DIR") or str(BASE_DIR / "data")).resolve()
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    TIMEZONE: ZoneInfo = ZoneInfo(os.getenv("TIMEZONE") or "Asia/Tashkent")
    DEBUG: bool = _bool("DEBUG", False)

    @classmethod
    def media_dir(cls) -> Path:
        p = cls.DATA_DIR / "media"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def db_url(cls) -> str:
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{(cls.DATA_DIR / 'atko.db').as_posix()}"


config = Config()
