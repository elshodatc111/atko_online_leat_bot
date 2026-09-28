"""Fayllarni saqlash: Telegramdan yuklab olish, paneldan yuklash, hajm cheklovlari."""
from __future__ import annotations

import asyncio
import mimetypes
import secrets
import shutil
from pathlib import Path

from ..config import config
from . import settings, worktime

KIND_LIMIT_KEY = {
    "photo": "max_photo_mb",
    "voice": "max_audio_mb",
    "audio": "max_audio_mb",
    "video": "max_video_mb",
    "video_note": "max_video_mb",
    "document": "max_document_mb",
    "animation": "max_video_mb",
}

TELEGRAM_DOWNLOAD_LIMIT_MB = 20  # Bot API getFile cheklovi
TELEGRAM_UPLOAD_LIMIT_MB = 50  # Bot API orqali yuborish cheklovi


async def limit_mb(kind: str) -> int:
    key = KIND_LIMIT_KEY.get(kind, "max_document_mb")
    return int(await settings.get(key) or 20)


def new_path(ext: str, sub: str = "chat") -> Path:
    now = worktime.now_local()
    folder = config.media_dir() / sub / now.strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    ext = ext if ext.startswith(".") or not ext else "." + ext
    return folder / f"{now.strftime('%d%H%M%S')}_{secrets.token_hex(4)}{ext}"


def rel(path: Path | str) -> str:
    """media papkasiga nisbatan yo'l (panelda URL uchun)."""
    p = Path(path).resolve()
    try:
        return p.relative_to(config.media_dir().resolve()).as_posix()
    except ValueError:
        return p.name


def abs_path(rel_path: str) -> Path | None:
    base = config.media_dir().resolve()
    p = (base / rel_path).resolve()
    if base not in p.parents and p != base:
        return None
    return p


def guess_ext(file_name: str | None, mime: str | None, default: str = ".bin") -> str:
    if file_name and "." in file_name:
        return "." + file_name.rsplit(".", 1)[1].lower()[:8]
    if mime:
        if mime == "audio/ogg":
            return ".ogg"
        ext = mimetypes.guess_extension(mime)
        if ext:
            return ext
    return default


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def to_ogg_opus(src: Path) -> Path | None:
    """Brauzer yozgan audioni (webm) Telegram voice formatiga (ogg/opus) o'tkazadi. ffmpeg bo'lmasa None."""
    if not ffmpeg_available():
        return None
    dst = src.with_suffix(".ogg")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(src), "-c:a", "libopus", "-b:a", "48k", str(dst),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return dst if proc.returncode == 0 and dst.exists() else None


def media_kind_from_mime(mime: str | None, file_name: str | None = None) -> str:
    mime = (mime or mimetypes.guess_type(file_name or "")[0] or "").lower()
    if mime.startswith("image/") and not mime.endswith("gif"):
        return "photo"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    return "document"
