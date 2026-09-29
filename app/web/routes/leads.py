"""Leadlar ro'yxati, kartasi, status va izohlar."""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, func, or_, select

from ...db import session_scope, utcnow
from ...models import LEAD_STATUSES, Chat, Lead, LeadComment, Message, Source, Staff
from ...services import audit, stats, worktime
from ...services.chats import message_dict
from ...services.notify import hub
from ..deps import admin_required, current_staff, flash, parse_range, render

router = APIRouter()
PER_PAGE = 50


@router.get("/leads")
async def leads_page(request: Request, q: str = "", status: str = "", source: str = "", temp: str = "",
                     start: str = "", end: str = "", page: int = 1, staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        query = select(Lead)
        if q:
            like = f"%{q}%"
            query = query.where(or_(Lead.name.ilike(like), Lead.phone.ilike(like), Lead.tg_username.ilike(like),
                                    Lead.tg_name.ilike(like)))
        if status:
            query = query.where(Lead.status == status)
        if source == "none":
            query = query.where(Lead.source_id.is_(None))
        elif source.isdigit():
            query = query.where(Lead.source_id == int(source))
        if temp:
            query = query.where(Lead.temperature == temp)
        if start or end:
            s0, s1 = stats.range_utc(*parse_range(start, end))
            query = query.where(Lead.created_at >= s0, Lead.created_at < s1)
        total = (await s.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        rows = (await s.execute(query.order_by(Lead.last_activity.desc()).offset((page - 1) * PER_PAGE).limit(PER_PAGE))).scalars().all()
        sources = (await s.execute(select(Source).order_by(Source.name))).scalars().all()
    return render(request, "leads.html", staff, leads=rows, total=total, page=page,
                  pages=max(1, math.ceil(total / PER_PAGE)), sources=sources,
                  f={"q": q, "status": status, "source": source, "temp": temp, "start": start, "end": end})


@router.get("/leads/{lead_id}")
async def lead_page(lead_id: int, request: Request, staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        if not lead:
            flash(request, "Lead topilmadi", "danger")
            return RedirectResponse("/leads", 303)
        msgs = (await s.execute(select(Message).where(Message.lead_id == lead_id).order_by(Message.id.desc()).limit(500))).scalars().all()
        comments = (await s.execute(select(LeadComment).where(LeadComment.lead_id == lead_id).order_by(LeadComment.id.desc()))).scalars().all()
        chats = (await s.execute(select(Chat).where(Chat.lead_id == lead_id).order_by(Chat.id.desc()))).scalars().all()
        sources = (await s.execute(select(Source).order_by(Source.name))).scalars().all()
    return render(request, "lead.html", staff, lead=lead, messages=[message_dict(m) for m in reversed(msgs)],
                  comments=comments, chats=chats, sources=sources)


async def _set_status(lead_id: int, staff: Staff, status: str, reason: str | None) -> str | None:
    if status not in LEAD_STATUSES:
        return "Noto'g'ri status"
    if status == "rejected" and not (reason or "").strip():
        return "Rad etish sababini ko'rsating"
    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        if not lead:
            return "Lead topilmadi"
        old = lead.status_label
        lead.status = status
        if status == "rejected":
            lead.reject_reason = reason.strip()[:255]
        if status == "accepted":
            lead.accepted_by_id = staff.id
            lead.accepted_at = utcnow()
            lead.reminders_stopped = True
        elif lead.accepted_by_id and status != "accepted":
            lead.accepted_by_id = None
            lead.accepted_at = None
        if status in ("rejected",):
            lead.reminders_stopped = True
        await audit.log(staff.id, "lead_status", "lead", lead_id, f"{old} → {LEAD_STATUSES[status]}" + (f" ({reason})" if reason else ""), session=s)
    await hub.emit("lead_updated", {"lead_id": lead_id, "status": status, "status_label": LEAD_STATUSES[status]})
    return None


async def _add_comment(lead_id: int, staff: Staff, text: str) -> LeadComment | None:
    text = (text or "").strip()
    if not text:
        return None
    async with session_scope() as s:
        c = LeadComment(lead_id=lead_id, staff_id=staff.id, text=text[:4000])
        s.add(c)
        await audit.log(staff.id, "lead_comment", "lead", lead_id, text[:200], session=s)
        await s.flush()
        await s.refresh(c, ["staff"])
    await hub.emit("lead_comment", {"lead_id": lead_id, "text": c.text, "staff": staff.full_name, "time": worktime.fmt(c.created_at)})
    return c


# --------------------------------------------------------------- JSON API (chat sahifasi uchun)


@router.post("/api/leads/{lead_id}/status")
async def api_status(lead_id: int, status: str = Form(...), reason: str = Form(""), staff: Staff = Depends(current_staff)):
    err = await _set_status(lead_id, staff, status, reason)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    return {"ok": True, "status_label": LEAD_STATUSES[status]}


@router.post("/api/leads/{lead_id}/comments")
async def api_comment(lead_id: int, text: str = Form(...), staff: Staff = Depends(current_staff)):
    c = await _add_comment(lead_id, staff, text)
    if not c:
        return JSONResponse({"ok": False, "error": "Bo'sh izoh"}, status_code=400)
    return {"ok": True, "id": c.id, "text": c.text, "staff": staff.full_name, "time": worktime.fmt(c.created_at)}


@router.post("/api/leads/{lead_id}/start-chat")
async def api_start_chat(lead_id: int, staff: Staff = Depends(current_staff)):
    """Operator o'zi leadga yozishni boshlaydi (lead karta sahifasidan)."""
    from ...services import chats as chat_svc

    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        if not lead:
            return JSONResponse({"ok": False, "error": "Lead topilmadi"}, status_code=404)
        if lead.is_blocked:
            return JSONResponse({"ok": False, "error": "Lead botni bloklagan — faqat qo'ng'iroq qilish mumkin"}, status_code=400)
        existing = await chat_svc.active_chat(s, lead_id)
    if existing:
        if existing.status == "waiting":
            try:
                await chat_svc.claim(existing.id, staff)
            except chat_svc.ChatError as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return {"ok": True, "chat_id": existing.id}
    chat, _, _ = await chat_svc.request_operator(lead_id, reason="user", note=f"Operator {staff.display_name} suhbat boshladi")
    try:
        await chat_svc.claim(chat.id, staff)
    except chat_svc.ChatError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True, "chat_id": chat.id}


# --------------------------------------------------------------- formalar (lead sahifasi)


@router.post("/leads/{lead_id}/status")
async def form_status(lead_id: int, request: Request, status: str = Form(...), reason: str = Form(""),
                      staff: Staff = Depends(current_staff)):
    err = await _set_status(lead_id, staff, status, reason)
    flash(request, err or "Status yangilandi", "danger" if err else "success")
    return RedirectResponse(f"/leads/{lead_id}", 303)


@router.post("/leads/{lead_id}/comment")
async def form_comment(lead_id: int, request: Request, text: str = Form(...), staff: Staff = Depends(current_staff)):
    await _add_comment(lead_id, staff, text)
    flash(request, "Izoh qo'shildi")
    return RedirectResponse(f"/leads/{lead_id}#comments", 303)


@router.post("/leads/{lead_id}/edit")
async def form_edit(lead_id: int, request: Request, name: str = Form(""), phone: str = Form(""), goal: str = Form(""),
                    study_format: str = Form(""), level: str = Form(""), city: str = Form(""),
                    interested_tariff: str = Form(""), temperature: str = Form(""), source_id: str = Form(""),
                    staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        if not lead:
            return RedirectResponse("/leads", 303)
        lead.name = name.strip() or None
        lead.phone = phone.strip() or None
        lead.goal = goal or None
        lead.study_format = study_format or None
        lead.level = level.strip() or None
        lead.city = city.strip() or None
        lead.interested_tariff = interested_tariff.strip() or None
        lead.temperature = temperature or None
        if staff.is_admin:
            lead.source_id = int(source_id) if source_id.isdigit() else None
        await audit.log(staff.id, "lead_edit", "lead", lead_id, None, session=s)
    flash(request, "Ma'lumotlar saqlandi")
    return RedirectResponse(f"/leads/{lead_id}", 303)


@router.post("/leads/{lead_id}/reminders")
async def form_reminders(lead_id: int, request: Request, staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        lead.reminders_stopped = not lead.reminders_stopped
        state = lead.reminders_stopped
    flash(request, "Eslatmalar to'xtatildi" if state else "Eslatmalar qayta yoqildi")
    return RedirectResponse(f"/leads/{lead_id}", 303)


@router.post("/leads/{lead_id}/delete")
async def form_delete(lead_id: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        if lead:
            name = lead.display
            await s.execute(delete(Lead).where(Lead.id == lead_id))
            await audit.log(staff.id, "lead_delete", "lead", lead_id, name, session=s)
    flash(request, "Lead o'chirildi")
    return RedirectResponse("/leads", 303)
