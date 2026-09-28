"""Telegram bot orqali kirish."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ...bot.instance import bot_username, deep_link
from ...db import session_scope, utcnow
from ...models import LoginToken, Staff
from ...services import audit
from ..deps import render

router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("staff_id"):
        return RedirectResponse("/", 303)
    return render(request, "login.html")


@router.post("/login/start")
async def login_start():
    token = secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:24]
    async with session_scope() as s:
        s.add(LoginToken(token=token))
    username = await bot_username()
    return {"token": token, "link": deep_link(username, f"login_{token}"), "bot": username}


@router.get("/login/check/{token}")
async def login_check(token: str, request: Request):
    async with session_scope() as s:
        lt = await s.get(LoginToken, token)
        if not lt:
            return JSONResponse({"status": "expired"})
        if lt.created_at < utcnow() - timedelta(minutes=10):
            return JSONResponse({"status": "expired"})
        if lt.status == "rejected":
            return JSONResponse({"status": "rejected"})
        if lt.status != "confirmed" or not lt.staff_id:
            return JSONResponse({"status": "pending"})
        staff = await s.get(Staff, lt.staff_id)
        if not staff or not staff.is_active:
            return JSONResponse({"status": "rejected"})
        lt.status = "used"
        staff_id = staff.id
        await audit.log(staff_id, "login", "staff", staff_id, request.client.host if request.client else None, session=s)
    request.session.clear()
    request.session["staff_id"] = staff_id
    return JSONResponse({"status": "ok"})


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
