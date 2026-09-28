"""Veb-panel: shablonlar, autentifikatsiya, yordamchilar."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates

from ..db import session_scope, utcnow
from ..models import (
    CHAT_STATUSES,
    FORMATS,
    GOALS,
    LEAD_STATUSES,
    REJECT_REASONS,
    TEMPERATURES,
    Staff,
)
from ..services import stats, worktime
from ..services.chats import REASON_LABELS

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
templates.env.globals.update(
    LEAD_STATUSES=LEAD_STATUSES, GOALS=GOALS, FORMATS=FORMATS, TEMPERATURES=TEMPERATURES,
    CHAT_STATUSES=CHAT_STATUSES, REJECT_REASONS=REJECT_REASONS, REASON_LABELS=REASON_LABELS,
)
templates.env.filters["dt"] = lambda v, p="%d.%m.%Y %H:%M": worktime.fmt(v, p)
templates.env.filters["secs"] = stats.human_seconds


class LoginRequired(Exception):
    pass


async def current_staff(request: Request) -> Staff:
    sid = request.session.get("staff_id")
    if not sid:
        raise LoginRequired()
    async with session_scope() as s:
        st = await s.get(Staff, int(sid))
        if not st or not st.is_active:
            request.session.clear()
            raise LoginRequired()
        now = utcnow()
        if not st.last_seen or (now - st.last_seen).total_seconds() > 60:
            st.last_seen = now
    return st


async def admin_required(staff: Staff = Depends(current_staff)) -> Staff:
    if not staff.is_admin:
        raise HTTPException(403, "Bu bo'lim faqat admin uchun")
    return staff


def flash(request: Request, text: str, level: str = "success") -> None:
    # yangi ro'yxat berib qayta yozamiz — joyida append qilinsa sessiya o'zgargani sezilmaydi
    request.session["_flash"] = [*request.session.get("_flash", []), {"text": text, "level": level}][-5:]


def pop_flash(request: Request) -> list[dict]:
    return request.session.pop("_flash", [])


def render(request: Request, name: str, staff: Staff | None = None, **ctx):
    ctx.update({"request": request, "me": staff, "flashes": pop_flash(request), "path": request.url.path})
    return templates.TemplateResponse(request, name, ctx)


def parse_range(start: str | None, end: str | None, default_days: int = 30) -> tuple[date, date]:
    today = worktime.now_local().date()
    try:
        e = date.fromisoformat(end) if end else today
    except ValueError:
        e = today
    try:
        s = date.fromisoformat(start) if start else e - timedelta(days=default_days - 1)
    except ValueError:
        s = e - timedelta(days=default_days - 1)
    if s > e:
        s, e = e, s
    return s, e
