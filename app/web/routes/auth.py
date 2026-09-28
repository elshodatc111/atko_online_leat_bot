"""Panelga kirish: Telegram ID → bot shu akkauntga 6 xonali kod yuboradi → kod kiritiladi."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select

from ...config import config
from ...db import session_scope, utcnow
from ...models import LoginCode, Staff
from ...services import audit
from ..deps import render

router = APIRouter()

CODE_TTL_MIN = 5
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60
_ip_hits: dict[str, deque] = defaultdict(deque)


def _hash(tg_id: int, code: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), f"{tg_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _rate_limited(ip: str, limit: int = 15, window: int = 600) -> bool:
    q = _ip_hits[ip]
    now = time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("staff_id"):
        return RedirectResponse("/", 303)
    return render(request, "login.html")


@router.post("/login/code")
async def login_code(request: Request, tg_id: str = Form(...)):
    """Kod so'rash. Javob har doim bir xil (ID ro'yxatda bor-yo'qligini oshkor qilmaslik uchun)."""
    if _rate_limited(_ip(request)):
        return JSONResponse({"ok": False, "error": "Juda ko'p urinish. 10 daqiqadan keyin qayta urinib ko'ring."}, status_code=429)
    raw = tg_id.strip()
    if not raw.lstrip("-").isdigit():
        return JSONResponse({"ok": False, "error": "Telegram ID faqat raqamlardan iborat bo'lishi kerak"}, status_code=400)
    uid = int(raw)
    generic = {"ok": True, "message": "Agar bu ID panel xodimiga tegishli bo'lsa, Telegramingizga tasdiqlash kodi yuborildi."}
    async with session_scope() as s:
        staff = (await s.execute(select(Staff).where(Staff.tg_id == uid, Staff.is_active.is_(True)))).scalars().first()
        if not staff:
            return generic
        last = (await s.execute(select(LoginCode).where(LoginCode.tg_id == uid).order_by(LoginCode.id.desc()).limit(1))).scalars().first()
        if last and not last.used and (utcnow() - last.created_at).total_seconds() < RESEND_SECONDS:
            wait = RESEND_SECONDS - int((utcnow() - last.created_at).total_seconds())
            return JSONResponse({"ok": False, "error": f"Kod yaqinda yuborildi. {wait} soniyadan keyin qayta so'rashingiz mumkin."}, status_code=429)
        code = f"{secrets.randbelow(1_000_000):06d}"
        s.add(LoginCode(tg_id=uid, code_hash=_hash(uid, code), expires_at=utcnow() + timedelta(minutes=CODE_TTL_MIN)))
        name = staff.full_name
    try:
        from ...bot.instance import get_bot

        await get_bot().send_message(
            uid,
            f"🔐 <b>ATKO panelga kirish kodi</b>\n\n<code>{code}</code>\n\n"
            f"👤 {name}\n⏳ Kod {CODE_TTL_MIN} daqiqa amal qiladi.\n🌐 IP: {_ip(request)}\n\n"
            "⚠️ Kodni hech kimga bermang. Agar siz so'ramagan bo'lsangiz, bu xabarga e'tibor bermang.",
        )
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Botdan kod yuborib bo'lmadi. Avval botga /start yozing va qayta urinib ko'ring."},
                            status_code=400)
    return generic


@router.post("/login/verify")
async def login_verify(request: Request, tg_id: str = Form(...), code: str = Form(...)):
    if _rate_limited(_ip(request) + ":v", limit=30):
        return JSONResponse({"ok": False, "error": "Juda ko'p urinish. Keyinroq urinib ko'ring."}, status_code=429)
    raw, code = tg_id.strip(), code.strip().replace(" ", "")
    if not raw.lstrip("-").isdigit() or not code.isdigit():
        return JSONResponse({"ok": False, "error": "Kod noto'g'ri"}, status_code=400)
    uid = int(raw)
    async with session_scope() as s:
        lc = (await s.execute(select(LoginCode).where(LoginCode.tg_id == uid, LoginCode.used.is_(False))
                              .order_by(LoginCode.id.desc()).limit(1))).scalars().first()
        if not lc or lc.expires_at < utcnow():
            return JSONResponse({"ok": False, "error": "Kod topilmadi yoki muddati o'tgan. Yangi kod so'rang."}, status_code=400)
        if lc.attempts >= MAX_ATTEMPTS:
            lc.used = True
            return JSONResponse({"ok": False, "error": "Urinishlar soni tugadi. Yangi kod so'rang."}, status_code=400)
        if not hmac.compare_digest(lc.code_hash, _hash(uid, code)):
            lc.attempts += 1
            left = MAX_ATTEMPTS - lc.attempts
            return JSONResponse({"ok": False, "error": f"Kod noto'g'ri. Qolgan urinishlar: {left}"}, status_code=400)
        lc.used = True
        staff = (await s.execute(select(Staff).where(Staff.tg_id == uid, Staff.is_active.is_(True)))).scalars().first()
        if not staff:
            return JSONResponse({"ok": False, "error": "Xodim topilmadi"}, status_code=400)
        staff_id = staff.id
        await audit.log(staff_id, "login", "staff", staff_id, _ip(request), session=s)
    request.session.clear()
    request.session["staff_id"] = staff_id
    return {"ok": True}


@router.get("/logout")
async def logout(request: Request):
    sid = request.session.get("staff_id")
    if sid:
        async with session_scope() as s:
            st = await s.get(Staff, int(sid))
            if st:
                st.is_online = False
        await audit.log(int(sid), "logout")
    request.session.clear()
    return RedirectResponse("/login", 303)
