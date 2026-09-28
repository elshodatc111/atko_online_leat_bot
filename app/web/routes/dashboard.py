"""Bosh sahifa, statistika, WebSocket, media fayllar."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from ...db import session_scope
from ...models import Chat, Staff
from ...services import ai, media, stats, worktime
from ...services.notify import hub
from ..deps import current_staff, parse_range, render

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, staff: Staff = Depends(current_staff)):
    d = await stats.dashboard()
    today = worktime.now_local().date()
    series = await stats.leads_series(today - timedelta(days=29), today)
    monthly = await stats.leads_monthly(12)
    sources = await stats.by_source(today - timedelta(days=29), today)
    goals = await stats.by_goal()
    mine = (await stats.operator_stats(today, today, staff.id))[0]
    usage = await ai.usage_today()
    async with session_scope() as s:
        waiting = (await s.execute(select(Chat).where(Chat.status == "waiting").order_by(Chat.sla_start).limit(10))).scalars().all()
    return render(request, "dashboard.html", staff, d=d, series=series, monthly=monthly, sources=sources, goals=goals,
                  mine=mine, waiting=waiting, usage=usage, working=await worktime.is_working_time(),
                  hours=await worktime.work_hours_text())


@router.get("/stats")
async def stats_page(request: Request, start: str = "", end: str = "", staff: Staff = Depends(current_staff)):
    s, e = parse_range(start, end, 30)
    ops = await stats.operator_stats(s, e, None if staff.is_admin else staff.id)
    daily = await stats.operator_series(s, e)
    monthly_start = (worktime.now_local().date().replace(day=1) - timedelta(days=330)).replace(day=1)
    monthly = await stats.operator_series(monthly_start, worktime.now_local().date(), monthly=True)
    leads = await stats.leads_series(s, e)
    leads_monthly = await stats.leads_monthly(12)
    sources = await stats.by_source(s, e)
    if not staff.is_admin:
        mine = {staff.display_name}
        daily["datasets"] = [x for x in daily["datasets"] if x["label"] in mine]
        monthly["datasets"] = [x for x in monthly["datasets"] if x["label"] in mine]
    return render(request, "stats.html", staff, ops=ops, daily=daily, monthly=monthly, leads=leads,
                  leads_monthly=leads_monthly, sources=sources, start=s.isoformat(), end=e.isoformat())


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    sid = ws.session.get("staff_id") if "session" in ws.scope else None
    if not sid:
        await ws.close(code=4401)
        return
    async with session_scope() as s:
        st = await s.get(Staff, int(sid))
    if not st or not st.is_active:
        await ws.close(code=4403)
        return
    await hub.connect(st.id, st.role, ws)
    try:
        while True:
            await ws.receive_text()  # ping
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        hub.disconnect(st.id, ws)


@router.get("/media/{path:path}")
async def media_file(path: str, staff: Staff = Depends(current_staff)):
    p = media.abs_path(path)
    if not p or not p.exists() or not p.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    mime = None
    if p.suffix.lower() in (".oga", ".ogg", ".opus"):
        mime = "audio/ogg"
    return FileResponse(p, media_type=mime)
