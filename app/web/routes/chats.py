"""Operator chatlari: sahifa va JSON API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from ...db import session_scope
from ...models import Chat, Lead, LeadComment, Message, Staff, Template
from ...services import ai, media, settings, worktime
from ...services import chats as chat_svc
from ...services.notify import hub
from ..deps import current_staff, render

router = APIRouter()


def _err(text: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": text}, status_code=code)


@router.get("/chats")
async def chats_page(request: Request, staff: Staff = Depends(current_staff)):
    return render(request, "chats.html", staff, open_chat=None)


@router.get("/chats/{chat_id}")
async def chat_page(chat_id: int, request: Request, staff: Staff = Depends(current_staff)):
    return render(request, "chats.html", staff, open_chat=chat_id)


@router.get("/api/chats")
async def api_chats(tab: str = "queue", q: str = "", staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        query = select(Chat)
        if tab == "queue":
            query = query.where(Chat.status == "waiting").order_by(Chat.sla_start)
        elif tab == "mine":
            query = query.where(Chat.status == "active", Chat.operator_id == staff.id).order_by(Chat.last_lead_msg_at.desc())
        elif tab == "active":
            query = query.where(Chat.status == "active").order_by(Chat.last_lead_msg_at.desc())
        else:
            query = query.where(Chat.status == "closed").order_by(Chat.closed_at.desc())
        if q:
            like = f"%{q}%"
            query = query.join(Lead, Lead.id == Chat.lead_id).where(
                (Lead.name.ilike(like)) | (Lead.phone.ilike(like)) | (Lead.tg_username.ilike(like)))
        rows = (await s.execute(query.limit(200))).scalars().all()
        counts = {
            "queue": (await s.execute(select(func.count(Chat.id)).where(Chat.status == "waiting"))).scalar_one(),
            "mine": (await s.execute(select(func.count(Chat.id)).where(Chat.status == "active", Chat.operator_id == staff.id))).scalar_one(),
            "active": (await s.execute(select(func.count(Chat.id)).where(Chat.status == "active"))).scalar_one(),
        }
        ids = [c.lead_id for c in rows]
        last_msgs = {}
        if ids:
            sub = select(Message.lead_id, func.max(Message.id)).where(Message.lead_id.in_(ids)).group_by(Message.lead_id)
            mids = [r[1] for r in (await s.execute(sub)).all()]
            if mids:
                for m in (await s.execute(select(Message).where(Message.id.in_(mids)))).scalars().all():
                    last_msgs[m.lead_id] = (chat_svc.plain(m.text) or m.transcript or f"[{m.kind}]")[:80]
    items = []
    for c in rows:
        d = chat_svc.chat_dict(c)
        d["last"] = last_msgs.get(c.lead_id, "")
        d["temperature"] = c.lead.temperature if c.lead else None
        items.append(d)
    return {"items": items, "counts": counts, "working": await worktime.is_working_time()}


@router.get("/api/chats/{chat_id}")
async def api_chat(chat_id: int, staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        if not chat:
            return _err("Chat topilmadi", 404)
        lead = chat.lead
        msgs = (await s.execute(select(Message).where(Message.lead_id == lead.id).order_by(Message.id.desc()).limit(300))).scalars().all()
        comments = (await s.execute(select(LeadComment).where(LeadComment.lead_id == lead.id).order_by(LeadComment.id.desc()))).scalars().all()
        history = (await s.execute(select(Chat).where(Chat.lead_id == lead.id).order_by(Chat.id.desc()).limit(20))).scalars().all()
        if chat.operator_id == staff.id and chat.unread:
            chat.unread = 0
    return {
        "chat": chat_svc.chat_dict(chat),
        "can_write": chat.status == "active" and (chat.operator_id == staff.id or staff.is_admin),
        "is_mine": chat.operator_id == staff.id,
        "lead": _lead_dict(lead),
        "messages": [chat_svc.message_dict(m) for m in reversed(msgs)],
        "comments": [{"id": c.id, "text": c.text, "staff": c.staff.full_name if c.staff else "—",
                      "time": worktime.fmt(c.created_at)} for c in comments],
        "history": [{"id": h.id, "status": h.status_label, "operator": h.operator.display_name if h.operator else "—",
                     "time": worktime.fmt(h.requested_at, "%d.%m.%Y %H:%M"), "rating": h.rating,
                     "comment": h.rating_comment} for h in history],
    }


def _lead_dict(lead: Lead) -> dict:
    from ...models import FORMATS, GOALS, TEMPERATURES

    return {
        "id": lead.id, "name": lead.display, "phone": lead.phone, "username": lead.tg_username, "tg_id": lead.tg_id,
        "lang": lead.lang, "status": lead.status, "status_label": lead.status_label,
        "goal": GOALS.get(lead.goal or "", {}).get("uz"), "format": FORMATS.get(lead.study_format or "", {}).get("uz"),
        "level": lead.level, "city": lead.city, "tariff": lead.interested_tariff,
        "source": lead.source.name if lead.source else None, "temperature": TEMPERATURES.get(lead.temperature or ""),
        "summary": lead.ai_summary, "reject_reason": lead.reject_reason, "blocked": lead.is_blocked,
        "trial": lead.trial_requested, "created": worktime.fmt(lead.created_at),
    }


@router.post("/api/chats/{chat_id}/claim")
async def api_claim(chat_id: int, staff: Staff = Depends(current_staff)):
    try:
        await chat_svc.claim(chat_id, staff)
    except chat_svc.ChatError as e:
        return _err(str(e))
    return {"ok": True}


@router.post("/api/chats/{chat_id}/close")
async def api_close(chat_id: int, staff: Staff = Depends(current_staff)):
    try:
        await chat_svc.close(chat_id, staff)
    except chat_svc.ChatError as e:
        return _err(str(e))
    return {"ok": True}


@router.post("/api/chats/{chat_id}/transfer")
async def api_transfer(chat_id: int, to_staff_id: int = Form(...), staff: Staff = Depends(current_staff)):
    try:
        await chat_svc.transfer(chat_id, staff, to_staff_id)
    except chat_svc.ChatError as e:
        return _err(str(e))
    return {"ok": True}


@router.post("/api/chats/{chat_id}/send")
async def api_send(chat_id: int, text: str = Form(...), staff: Staff = Depends(current_staff)):
    try:
        m = await chat_svc.operator_send_text(chat_id, staff, text)
    except chat_svc.ChatError as e:
        return _err(str(e))
    return {"ok": True, "id": m.id}


@router.post("/api/chats/{chat_id}/upload")
async def api_upload(chat_id: int, file: UploadFile = File(...), caption: str = Form(""), as_voice: bool = Form(False),
                     staff: Staff = Depends(current_staff)):
    mime = file.content_type or ""
    kind = "voice" if as_voice else media.media_kind_from_mime(mime, file.filename)
    limit = min(await media.limit_mb(kind), media.TELEGRAM_UPLOAD_LIMIT_MB)
    path = media.new_path(media.guess_ext(file.filename, mime), "chat")
    size = 0
    with path.open("wb") as fh:
        while chunk := await file.read(1024 * 256):
            size += len(chunk)
            if size > limit * 1024 * 1024:
                fh.close()
                path.unlink(missing_ok=True)
                return _err(f"Fayl juda katta. Ruxsat etilgan hajm: {limit} MB")
            fh.write(chunk)
    try:
        await chat_svc.operator_send_file(chat_id, staff, path, file.filename or path.name, mime, caption or None, as_voice)
    except chat_svc.ChatError as e:
        return _err(str(e))
    return {"ok": True}


@router.post("/api/chats/{chat_id}/suggest")
async def api_suggest(chat_id: int, staff: Staff = Depends(current_staff)):
    if not await ai.is_available():
        return _err("AI o'chirilgan yoki kunlik limit tugagan")
    try:
        text = await ai.suggest_reply(chat_id)
    except Exception as e:  # noqa: BLE001
        return _err(f"AI xatosi: {e}")
    return {"ok": True, "text": text}


@router.post("/api/chats/{chat_id}/summary")
async def api_summary(chat_id: int, staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
    if not chat:
        return _err("Chat topilmadi", 404)
    data = await ai.summarize_lead(chat.lead_id)
    if not data:
        return _err("AI xulosa tayyorlay olmadi")
    return {"ok": True, **data}


@router.get("/api/staff/available")
async def api_staff(staff: Staff = Depends(current_staff)):
    max_chats = int(await settings.get("max_chats_per_operator") or 5)
    async with session_scope() as s:
        rows = (await s.execute(select(Staff).where(Staff.is_active.is_(True)).order_by(Staff.full_name))).scalars().all()
        out = []
        for st in rows:
            load = await chat_svc.operator_load(s, st.id)
            out.append({"id": st.id, "name": st.full_name, "display": st.display_name, "online": st.is_online or st.id in hub.online_ids(),
                        "load": load, "max": max_chats, "me": st.id == staff.id})
    return {"items": out}


@router.get("/api/templates")
async def api_templates(staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        rows = (await s.execute(select(Template).order_by(Template.sort, Template.id))).scalars().all()
    return {"items": [{"id": x.id, "title": x.title, "uz": x.text_uz, "ru": x.text_ru} for x in rows]}


@router.post("/api/me/online")
async def api_online(online: bool = Form(...), staff: Staff = Depends(current_staff)):
    from ...services import audit

    async with session_scope() as s:
        st = await s.get(Staff, staff.id)
        st.is_online = online
    await audit.log(staff.id, "online", "staff", staff.id, "Onlayn" if online else "Oflayn")
    await hub.emit("staff_online", {"id": staff.id, "online": online})
    return {"ok": True, "online": online}


@router.get("/api/me/counters")
async def api_counters(staff: Staff = Depends(current_staff)):
    async with session_scope() as s:
        waiting = (await s.execute(select(func.count(Chat.id)).where(Chat.status == "waiting"))).scalar_one()
        mine_unread = (await s.execute(select(func.coalesce(func.sum(Chat.unread), 0)).where(
            Chat.status == "active", Chat.operator_id == staff.id))).scalar_one()
    return {"waiting": waiting, "unread": int(mine_unread or 0)}
