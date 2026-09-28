"""Tizim holati: har bir qismni tekshirish, xatolar jurnali, avtomatik tuzatish va ogohlantirish."""
from __future__ import annotations

import collections
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from ..config import config
from ..db import engine, session_scope
from ..models import Chat, Lead, Payment, Subscription
from . import settings, worktime

log = logging.getLogger(__name__)

started_at = time.time()
last_update_at: float | None = None  # botga oxirgi update kelgan vaqt
loops: dict[str, dict[str, Any]] = {}
_last_status: dict[str, str] = {}


# ------------------------------------------------------------------ xatolar jurnali (xotirada)

errors: collections.deque = collections.deque(maxlen=100)


class _ErrorHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info and record.exc_info[1]:
                msg += f" — {type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
            errors.appendleft({"time": time.time(), "logger": record.name, "level": record.levelname, "message": msg[:1000]})
        except Exception:  # noqa: BLE001
            pass


def install_error_handler() -> None:
    root = logging.getLogger()
    if not any(isinstance(h, _ErrorHandler) for h in root.handlers):
        h = _ErrorHandler(level=logging.ERROR)
        root.addHandler(h)


def loop_mark(name: str, ok: bool, error: str | None = None) -> None:
    st = loops.setdefault(name, {"runs": 0, "errors": 0})
    st["last_run"] = time.time()
    st["runs"] += 1
    if ok:
        st["last_ok"] = time.time()
    else:
        st["errors"] += 1
        st["last_error"] = (error or "")[:500]
        st["last_error_at"] = time.time()


def ago(ts: float | None) -> str:
    if not ts:
        return "hali yo'q"
    sec = int(time.time() - ts)
    if sec < 60:
        return f"{sec} s oldin"
    if sec < 3600:
        return f"{sec // 60} daq oldin"
    if sec < 86400:
        return f"{sec // 3600} soat oldin"
    return f"{sec // 86400} kun oldin"


def _c(key: str, title: str, status: str, details: str, fixes: list[tuple[str, str]] | None = None, hint: str | None = None) -> dict:
    return {"key": key, "title": title, "status": status, "details": details, "fixes": fixes or [], "hint": hint}


# ------------------------------------------------------------------ tekshiruvlar


async def check_bot() -> list[dict]:
    from ..bot import setup as bot_setup
    from ..bot.instance import get_bot

    out = []
    if not config.BOT_TOKEN:
        return [_c("bot", "🤖 Telegram bot", "fail", "BOT_TOKEN .env faylida ko'rsatilmagan",
                   hint=".env fayliga BOT_TOKEN ni yozing va dasturni qayta ishga tushiring")]
    try:
        me = await get_bot().get_me()
        out.append(_c("bot", "🤖 Telegram bot", "ok", f"@{me.username} ulangan · rejim: {config.BOT_MODE} · oxirgi xabar: {ago(last_update_at)}",
                      [("restart_bot", "Botni qayta ulash")]))
    except Exception as e:  # noqa: BLE001
        out.append(_c("bot", "🤖 Telegram bot", "fail", f"Telegram bilan aloqa yo'q: {e}", [("restart_bot", "Botni qayta ulash")],
                      "Token to'g'riligini va internet aloqasini tekshiring"))
        return out
    if config.BOT_MODE == "webhook":
        try:
            info = await get_bot().get_webhook_info()
            expected = config.WEBHOOK_BASE_URL + bot_setup.webhook_path()
            if info.url != expected:
                out.append(_c("webhook", "🔗 Webhook", "fail", f"Webhook manzili noto'g'ri: {info.url or 'o‘rnatilmagan'}",
                              [("reset_webhook", "Webhook'ni qayta o'rnatish")]))
            elif info.last_error_message:
                out.append(_c("webhook", "🔗 Webhook", "warn",
                              f"Oxirgi xato: {info.last_error_message} · navbatda: {info.pending_update_count}",
                              [("reset_webhook", "Webhook'ni qayta o'rnatish")]))
            else:
                out.append(_c("webhook", "🔗 Webhook", "ok", f"O'rnatilgan · navbatda: {info.pending_update_count}",
                              [("reset_webhook", "Qayta o'rnatish")]))
        except Exception as e:  # noqa: BLE001
            out.append(_c("webhook", "🔗 Webhook", "fail", str(e), [("reset_webhook", "Webhook'ni qayta o'rnatish")]))
    else:
        alive = bot_setup.polling_alive()
        out.append(_c("polling", "🔄 Polling (xabarlarni qabul qilish)", "ok" if alive else "fail",
                      "Ishlayapti" if alive else "To'xtab qolgan — xabarlar qabul qilinmayapti",
                      [("restart_bot", "Qayta ishga tushirish")]))
    return out


async def check_group() -> dict:
    from ..bot.instance import get_bot
    from . import subscriptions

    gid = await subscriptions.group_id()
    if not gid:
        return _c("group", "👥 Yopiq Premium guruh", "warn", "Guruh tanlanmagan",
                  hint="Botni guruhga admin qilib qo'shing, so'ng Sozlamalar → «Yopiq guruh» bo'limida guruhni tanlang")
    try:
        bot = get_bot()
        chat = await bot.get_chat(gid)
        me = await bot.get_me()
        m = await bot.get_chat_member(gid, me.id)
        status = m.status if isinstance(m.status, str) else m.status.value
        count = await bot.get_chat_member_count(gid)
        if status != "administrator":
            return _c("group", "👥 Yopiq Premium guruh", "fail", f"«{chat.title}»: bot admin emas (holat: {status})",
                      [("check_group", "Qayta tekshirish")], "Guruh sozlamalarida botni admin qiling")
        missing = []
        if not getattr(m, "can_invite_users", False):
            missing.append("«Havola orqali taklif qilish»")
        if not getattr(m, "can_restrict_members", False):
            missing.append("«Foydalanuvchilarni bloklash»")
        if missing:
            return _c("group", "👥 Yopiq Premium guruh", "fail", f"«{chat.title}»: botda {', '.join(missing)} huquqi yo'q",
                      [("check_group", "Qayta tekshirish")], "Guruh → Adminlar → bot → shu huquqlarni yoqing")
        return _c("group", "👥 Yopiq Premium guruh", "ok", f"«{chat.title}» · a'zolar: {count} · bot huquqlari to'liq",
                  [("sync_group", "A'zolarni sinxronlash"), ("run_sub_check", "Obunalarni hozir tekshirish")])
    except Exception as e:  # noqa: BLE001
        return _c("group", "👥 Yopiq Premium guruh", "fail", f"Guruhga ulanib bo'lmadi: {e}", [("check_group", "Qayta tekshirish")],
                  "Guruh ID to'g'riligini va bot guruhda ekanini tekshiring")


async def check_ai(deep: bool = False) -> list[dict]:
    from . import ai

    out = []
    key = await ai.api_key()
    enabled = await settings.get("ai_enabled")
    u = await ai.usage_today()
    limit = int(await settings.get("ai_daily_token_limit") or 0)
    used = u.input_tokens + u.output_tokens
    usage = f"bugun {u.requests} so'rov, {used:,} token".replace(",", " ") + (f" / limit {limit:,}".replace(",", " ") if limit else "")
    if not key:
        out.append(_c("ai", "🧠 OpenAI", "fail", "API kalit kiritilmagan", hint="Sozlamalar → OpenAI bo'limida kalitni kiriting"))
    elif not enabled:
        out.append(_c("ai", "🧠 OpenAI", "warn", "AI o'chirilgan (Sozlamalar)"))
    elif limit and used >= limit:
        out.append(_c("ai", "🧠 OpenAI", "warn", f"Kunlik token limiti tugagan — {usage}", hint="Sozlamalar → kunlik limitni oshiring"))
    else:
        status, details = ("warn" if u.errors else "ok"), f"Model: {await settings.get('ai_model')} · {usage} · xatolar: {u.errors}"
        if deep:
            try:
                msg = await ai.complete([{"role": "user", "content": "OK deb javob bering."}], max_tokens=300)
                details += f" · sinov: ✅ «{(msg.content or '').strip()[:40]}»"
                status = "ok"
            except Exception as e:  # noqa: BLE001
                status, details = "fail", f"Sinov so'rovi xatosi: {e}"
        out.append(_c("ai", "🧠 OpenAI", status, details, [("test_ai", "AI ni sinash")]))
    stores = await ai.vector_store_ids()
    if not stores:
        out.append(_c("vs", "📚 AI mentor darsliklari (Vector store)", "warn", "Vector store ID kiritilmagan — AI mentor darsliklarsiz javob beradi",
                      hint="platform.openai.com → Storage → Vector stores → ID ni Sozlamalarga kiriting"))
    elif key:
        try:
            client = await ai.get_client()
            parts = []
            for sid in stores:
                vs = await client.vector_stores.retrieve(sid)
                fc = getattr(vs, "file_counts", None)
                parts.append(f"{getattr(vs, 'name', sid) or sid}: {getattr(fc, 'completed', '?')} ta fayl")
            out.append(_c("vs", "📚 AI mentor darsliklari (Vector store)", "ok", " · ".join(parts)))
        except Exception as e:  # noqa: BLE001
            out.append(_c("vs", "📚 AI mentor darsliklari (Vector store)", "fail", f"Vector store topilmadi: {e}"))
    return out


async def check_payme() -> dict:
    from . import payme

    mid = await payme.merchant_id()
    key = await payme.active_key()
    mode = "TEST" if await payme.test_mode() else "ISHCHI"
    endpoint = f"{config.PANEL_URL}/payme"
    async with session_scope() as s:
        last = (await s.execute(select(Payment).where(Payment.state == 2).order_by(Payment.paid_at.desc()).limit(1))).scalars().first()
    last_txt = f"oxirgi to'lov: {worktime.fmt(last.paid_at)}" if last else "hali to'lov yo'q"
    if not mid or not key:
        return _c("payme", "💳 Payme", "warn", f"Rejim: {mode} · Merchant ID yoki kalit kiritilmagan",
                  hint="Sozlamalar → Payme bo'limini to'ldiring")
    details = f"Rejim: {mode} · Endpoint: {endpoint} · Payme so'rovi: {ago(payme.last_request_at)} · {last_txt}"
    if payme.last_error:
        return _c("payme", "💳 Payme", "warn", details + f" · oxirgi xato: {payme.last_error}")
    if "localhost" in endpoint or "127.0.0.1" in endpoint:
        return _c("payme", "💳 Payme", "warn", details, hint="Payme localhost'ga ulana olmaydi — ngrok yoki server manzilini PANEL_URL ga yozing")
    return _c("payme", "💳 Payme", "ok", details)


async def check_db() -> dict:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        async with session_scope() as s:
            leads = (await s.execute(select(func.count(Lead.id)))).scalar_one()
            subs = (await s.execute(select(func.count(Subscription.id)))).scalar_one()
        db_path = config.DATA_DIR / "atko.db"
        size = db_path.stat().st_size / 1024 / 1024 if db_path.exists() else 0
        return _c("db", "🗄 Ma'lumotlar bazasi", "ok", f"SQLite · {size:.1f} MB · leadlar: {leads} · obunachilar: {subs}")
    except Exception as e:  # noqa: BLE001
        return _c("db", "🗄 Ma'lumotlar bazasi", "fail", str(e))


def check_disk() -> dict:
    try:
        total, used, free = shutil.disk_usage(config.DATA_DIR)
        media = sum(f.stat().st_size for f in Path(config.media_dir()).rglob("*") if f.is_file()) / 1024 / 1024
        free_gb = free / 1024**3
        return _c("disk", "💾 Disk", "ok" if free_gb > 1 else ("warn" if free_gb > 0.2 else "fail"),
                  f"Bo'sh joy: {free_gb:.1f} GB · media fayllar: {media:.1f} MB")
    except Exception as e:  # noqa: BLE001
        return _c("disk", "💾 Disk", "warn", str(e))


def check_loops() -> dict:
    from . import scheduler

    dead = scheduler.dead_loops()
    parts = []
    for name, title in scheduler.LOOP_TITLES.items():
        st = loops.get(name, {})
        mark = "❌" if name in dead else ("⚠️" if st.get("last_error_at") and st.get("last_error_at", 0) >= st.get("last_ok", 0) else "✅")
        parts.append(f"{mark} {title}: {ago(st.get('last_run'))}")
    status = "fail" if dead else ("warn" if any("⚠️" in p for p in parts) else "ok")
    return _c("loops", "⏱ Fon vazifalari", status, " · ".join(parts), [("restart_scheduler", "Qayta ishga tushirish")])


async def check_queue() -> dict:
    async with session_scope() as s:
        waiting = (await s.execute(select(func.count(Chat.id)).where(Chat.status == "waiting"))).scalar_one()
    from .notify import hub

    online = len(hub.online_ids())
    status = "warn" if waiting and not online and await worktime.is_working_time() else "ok"
    return _c("ops", "👨‍💼 Operatorlar", status, f"Panelda: {online} kishi · navbatda: {waiting} murojaat")


async def all_checks(deep: bool = False) -> list[dict]:
    from .media import ffmpeg_available

    items: list[dict] = []
    items += await check_bot()
    items.append(await check_group())
    items += await check_ai(deep)
    items.append(await check_payme())
    items.append(await check_db())
    items.append(check_disk())
    items.append(check_loops())
    items.append(await check_queue())
    items.append(_c("ffmpeg", "🎙 ffmpeg (ixtiyoriy)", "ok" if ffmpeg_available() else "warn",
                    "O'rnatilgan — operator ovozli xabari «voice» bo'lib boradi" if ffmpeg_available()
                    else "O'rnatilmagan — operator ovozli xabari audio fayl bo'lib boradi (bu normal)"))
    return items


# ------------------------------------------------------------------ tuzatish amallari


async def run_fix(action: str) -> str:
    from . import ai, scheduler, subscriptions

    if action == "restart_bot":
        from ..bot import setup as bot_setup

        await bot_setup.restart_bot()
        return "Bot qayta ulandi"
    if action == "reset_webhook":
        from ..bot import setup as bot_setup

        await bot_setup.reset_webhook()
        return "Webhook qayta o'rnatildi"
    if action == "restart_scheduler":
        await scheduler.restart()
        return "Fon vazifalari qayta ishga tushirildi"
    if action == "test_ai":
        res = await check_ai(deep=True)
        return res[0]["details"]
    if action == "check_group":
        return (await check_group())["details"]
    if action == "sync_group":
        r = await subscriptions.sync_group()
        return f"Sinxronlandi: {r['total']} obunachidan {r['in_group']} tasi guruhda"
    if action == "run_sub_check":
        r = await subscriptions.daily_check()
        return f"Tekshirildi: {r['reminded']} ta eslatma, {r['removed']} ta chiqarildi"
    if action == "clear_errors":
        errors.clear()
        return "Xatolar jurnali tozalandi"
    return "Noma'lum amal"


async def monitor() -> None:
    """Har 5 daqiqada: avtomatik tuzatish va holat o'zgarsa adminga Telegram xabari."""
    from ..bot import setup as bot_setup
    from . import scheduler
    from .notify import hub, telegram_staff

    # avtomatik tuzatish
    if config.BOT_TOKEN and config.BOT_MODE != "webhook" and not bot_setup.polling_alive():
        log.warning("Polling to'xtagan — avtomatik qayta ishga tushirilmoqda")
        await bot_setup.restart_bot()
    if scheduler.dead_loops():
        log.warning("Fon vazifasi to'xtagan — qayta ishga tushirilmoqda")
        await scheduler.restart(keep_monitor=True)
    items = await check_bot()
    items.append(await check_group())
    items.append(await check_db())
    for it in items:
        prev = _last_status.get(it["key"])
        _last_status[it["key"]] = it["status"]
        if prev is None or prev == it["status"]:
            continue
        if it["status"] == "fail":
            text_ = f"🔴 <b>Tizimda muammo:</b> {it['title']}\n{it['details']}" + (f"\n💡 {it['hint']}" if it.get("hint") else "")
        elif prev == "fail":
            text_ = f"🟢 <b>Tiklandi:</b> {it['title']}\n{it['details']}"
        else:
            continue
        await hub.emit("alert", {"level": "danger" if it["status"] == "fail" else "success", "text": f"{it['title']}: {it['details']}"},
                       admins_only=True)
        try:
            await telegram_staff(text_, admins=True, path="/system")
        except Exception:  # noqa: BLE001
            pass
