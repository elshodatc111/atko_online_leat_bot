"""ATKO Lead platforma."""
import os as _os


def _low_memory() -> bool:
    v = _os.getenv("LOW_MEMORY")
    if v is None:
        try:
            from pathlib import Path

            from dotenv import dotenv_values

            v = dotenv_values(Path(__file__).resolve().parent.parent / ".env").get("LOW_MEMORY")
        except Exception:  # noqa: BLE001
            v = None
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


if _low_memory():
    # bepul hosting uchun: aiogram import qilinishidan oldin yoqilishi shart
    from . import lowmem as _lowmem

    _lowmem.enable()
