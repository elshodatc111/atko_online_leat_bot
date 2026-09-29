"""Admin bo'limlari: operatorlar, manbalar, ommaviy xabar, sozlamalar, jurnal, eksport."""
from __future__ import annotations

import asyncio
import io
import math
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select

from ...bot.instance import bot_username, deep_link
from ...bot.texts import EDITABLE, TEXTS
from ...config import config
from ...db import session_scope, utcnow
from ...models import AiUsage, AuditLog, Broadcast, Holiday, Lead, Source, Staff
from ...services import ai, audit, broadcast, excel, media, settings, stats, worktime
from ..deps import admin_required, current_staff, flash, parse_range, render

router = APIRouter()


# ================================================================ operatorlar


@router.get("/operators")
async def operators_page(request: Request, staff: Staff = Depends(admin_required)):
    today = worktime.now_local().date()
    month = await stats.operator_stats(today.replace(day=1), today)
    today_stats = {x["id"]: x for x in await stats.operator_stats(today, today)}
    from ...services.notify import hub

    async with session_scope() as s:
        rows = (await s.execute(select(Staff).order_by(Staff.is_active.desc(), Staff.role, Staff.full_name))).scalars().all()
    username = await bot_username()
    invites = {st.id: deep_link(username, f"inv_{st.invite_token}") for st in rows if st.invite_token}
    return render(request, "admin/operators.html", staff, rows=rows, month={x["id"]: x for x in month},
                  today=today_stats, invites=invites, online=hub.online_ids())


@router.post("/operators/add")
async def operator_add(request: Request, full_name: str = Form(...), display_name: str = Form(...),
                       role: str = Form("operator"), tg_id: str = Form(""), staff: Staff = Depends(admin_required)):
    tg = int(tg_id) if tg_id.strip().lstrip("-").isdigit() else None
    async with session_scope() as s:
        if tg and (await s.execute(select(Staff).where(Staff.tg_id == tg))).scalars().first():
            flash(request, "Bu Telegram ID allaqachon ro'yxatda", "danger")
            return RedirectResponse("/operators", 303)
        st = Staff(full_name=full_name.strip(), display_name=display_name.strip(), role="admin" if role == "admin" else "operator",
                   tg_id=tg)
        if not tg:
            st.invite_token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")
            st.invite_expires = utcnow() + timedelta(days=7)
        s.add(st)
        await s.flush()
        await audit.log(staff.id, "operator_add", "staff", st.id, f"{st.full_name} ({st.role})", session=s)
    flash(request, "Xodim qo'shildi" + ("" if tg else ". Taklif havolasini unga yuboring (7 kun amal qiladi)."))
    return RedirectResponse("/operators", 303)


@router.post("/operators/{sid}/edit")
async def operator_edit(sid: int, request: Request, full_name: str = Form(...), display_name: str = Form(...),
                        role: str = Form("operator"), staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        st = await s.get(Staff, sid)
        if st:
            st.full_name, st.display_name = full_name.strip(), display_name.strip()
            if st.id != staff.id:
                st.role = "admin" if role == "admin" else "operator"
            await audit.log(staff.id, "operator_edit", "staff", sid, st.full_name, session=s)
    flash(request, "Saqlandi")
    return RedirectResponse("/operators", 303)


@router.post("/operators/{sid}/toggle")
async def operator_toggle(sid: int, request: Request, staff: Staff = Depends(admin_required)):
    if sid == staff.id:
        flash(request, "O'zingizni o'chira olmaysiz", "danger")
        return RedirectResponse("/operators", 303)
    async with session_scope() as s:
        st = await s.get(Staff, sid)
        if st:
            st.is_active = not st.is_active
            st.is_online = False
            await audit.log(staff.id, "operator_edit" if st.is_active else "operator_delete", "staff", sid,
                            f"{st.full_name}: {'faollashtirildi' if st.is_active else 'o`chirildi'}", session=s)
            msg = "Xodim qayta faollashtirildi" if st.is_active else "Xodim o'chirildi (statistikasi saqlanadi)"
    flash(request, msg)
    return RedirectResponse("/operators", 303)


@router.post("/operators/{sid}/invite")
async def operator_invite(sid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        st = await s.get(Staff, sid)
        if st:
            st.invite_token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")
            st.invite_expires = utcnow() + timedelta(days=7)
            st.tg_id = None
    flash(request, "Yangi taklif havolasi yaratildi. Eski Telegram akkaunt uzildi.")
    return RedirectResponse("/operators", 303)


# ================================================================ manbalar


@router.get("/sources")
async def sources_page(request: Request, staff: Staff = Depends(admin_required)):
    today = worktime.now_local().date()
    async with session_scope() as s:
        rows = (await s.execute(select(Source).order_by(Source.id))).scalars().all()
        counts = dict((await s.execute(select(Lead.source_id, func.count(Lead.id)).group_by(Lead.source_id))).all())
        acc = dict((await s.execute(select(Lead.source_id, func.count(Lead.id)).where(Lead.status == "accepted").group_by(Lead.source_id))).all())
        phones = dict((await s.execute(select(Lead.source_id, func.count(Lead.id)).where(Lead.phone.is_not(None)).group_by(Lead.source_id))).all())
    username = await bot_username()
    links = {x.id: deep_link(username, x.code) for x in rows}
    month = await stats.by_source(today - timedelta(days=29), today)
    return render(request, "admin/sources.html", staff, rows=rows, counts=counts, acc=acc, phones=phones, links=links,
                  direct=counts.get(None, 0), bot_link=f"https://t.me/{username}", month=month)


@router.post("/sources/add")
async def source_add(request: Request, code: str = Form(...), name: str = Form(...), note: str = Form(""),
                     staff: Staff = Depends(admin_required)):
    import re

    code = re.sub(r"[^a-zA-Z0-9_\-]", "", code.strip())[:64]
    if not code:
        flash(request, "Kod faqat lotin harflari, raqam, _ va - dan iborat bo'lishi kerak", "danger")
        return RedirectResponse("/sources", 303)
    async with session_scope() as s:
        if (await s.execute(select(Source).where(Source.code == code))).scalars().first():
            flash(request, "Bu kod mavjud", "danger")
            return RedirectResponse("/sources", 303)
        s.add(Source(code=code, name=name.strip(), note=note.strip() or None))
        await audit.log(staff.id, "source_add", "source", None, f"{name} ({code})", session=s)
    flash(request, "Manba qo'shildi")
    return RedirectResponse("/sources", 303)


@router.post("/sources/{sid}/edit")
async def source_edit(sid: int, request: Request, name: str = Form(...), note: str = Form(""),
                      staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(Source, sid)
        if x:
            x.name, x.note = name.strip(), note.strip() or None
            await audit.log(staff.id, "source_edit", "source", sid, name, session=s)
    flash(request, "Saqlandi")
    return RedirectResponse("/sources", 303)


@router.get("/sources/{sid}/qr.svg")
async def source_qr(sid: int, staff: Staff = Depends(admin_required)):
    import qrcode
    import qrcode.image.svg

    async with session_scope() as s:
        x = await s.get(Source, sid)
    link = deep_link(await bot_username(), x.code if x else "")
    img = qrcode.make(link, image_factory=qrcode.image.svg.SvgPathImage, box_size=12)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml",
                    headers={"Content-Disposition": f'inline; filename="qr_{x.code if x else sid}.svg"'})


# ================================================================ ommaviy xabar


@router.get("/broadcasts")
async def broadcasts_page(request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        rows = (await s.execute(select(Broadcast).order_by(Broadcast.id.desc()).limit(50))).scalars().all()
    counts = {k: len(await broadcast.recipients(k)) for k in broadcast.SEGMENTS}
    return render(request, "admin/broadcasts.html", staff, rows=rows, counts=counts, segments=broadcast.SEGMENTS,
                  kinds=broadcast.KINDS)


@router.post("/broadcasts/send")
async def broadcast_send(request: Request, segment: str = Form(...), kind: str = Form("text"), text: str = Form(...),
                         action: str = Form("test"), file: UploadFile | None = File(None),
                         staff: Staff = Depends(admin_required)):
    if segment not in broadcast.SEGMENTS or kind not in broadcast.KINDS:
        flash(request, "Noto'g'ri parametr", "danger")
        return RedirectResponse("/broadcasts", 303)
    text = text.strip()
    if kind != "text" and len(text) > 1024:
        flash(request, "Rasm/video bilan matn 1024 belgidan oshmasligi kerak (Telegram cheklovi)", "danger")
        return RedirectResponse("/broadcasts", 303)
    file_path = None
    if kind != "text":
        if not file or not file.filename:
            flash(request, "Rasm yoki video faylni tanlang", "danger")
            return RedirectResponse("/broadcasts", 303)
        limit = 10 if kind == "photo" else media.TELEGRAM_UPLOAD_LIMIT_MB
        data = await file.read()
        if len(data) > limit * 1024 * 1024:
            flash(request, f"Fayl juda katta (maks. {limit} MB)", "danger")
            return RedirectResponse("/broadcasts", 303)
        p = media.new_path(media.guess_ext(file.filename, file.content_type), "broadcast")
        p.write_bytes(data)
        file_path = str(p)
    if action == "test":
        try:
            await broadcast.send_one(staff.tg_id, kind, text, file_path, {})
            flash(request, "Sinov xabari Telegramingizga yuborildi ✅. Hammasi to'g'ri bo'lsa, «Yuborish» tugmasini bosing.")
        except Exception as e:  # noqa: BLE001
            flash(request, f"Sinov xabari yuborilmadi: {e}", "danger")
        request.session["bc_draft"] = {"segment": segment, "kind": kind, "text": text}
        return RedirectResponse("/broadcasts", 303)
    async with session_scope() as s:
        b = Broadcast(segment=segment, kind=kind, text=text, file_path=file_path, created_by_id=staff.id, status="running")
        s.add(b)
        await s.flush()
        bid = b.id
        await audit.log(staff.id, "broadcast_start", "broadcast", bid, f"{broadcast.SEGMENTS[segment]} / {broadcast.KINDS[kind]}", session=s)
    broadcast.start(bid)
    request.session.pop("bc_draft", None)
    flash(request, "Ommaviy xabar yuborish boshlandi")
    return RedirectResponse("/broadcasts", 303)


@router.post("/broadcasts/{bid}/cancel")
async def broadcast_cancel(bid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        b = await s.get(Broadcast, bid)
        if b and b.status == "running":
            b.status = "cancelled"
    flash(request, "To'xtatildi")
    return RedirectResponse("/broadcasts", 303)


# ================================================================ sozlamalar

INT_KEYS = ["max_chats_per_operator", "sla_wait_minutes", "idle_reply_minutes", "max_photo_mb", "max_audio_mb",
            "max_video_mb", "max_document_mb", "ai_daily_token_limit", "ai_history_messages", "tutor_trial_daily",
            "faq_auto_hour", "faq_min_count", "payme_vat_percent", "pay_reminder_minutes"]
FLOAT_KEYS = ["ai_price_input_per_1m", "ai_price_output_per_1m"]
BOOL_KEYS = ["sla_notify_lead", "ai_enabled", "ai_transcribe_voice", "ai_auto_escalate", "tutor_enabled",
             "faq_auto_enabled", "reminders_enabled", "payme_test_mode", "group_kick_unpaid", "pay_reminder_enabled"]
STR_KEYS = ["work_start", "work_end", "ai_model", "ai_transcribe_model", "ai_embedding_model", "ai_reasoning_effort",
            "ai_extra_instructions", "reminder_hours_from", "reminder_hours_to", "ai_vector_store_ids",
            "payme_merchant_id", "payme_account_field", "payme_ikpu", "payme_package_code", "payme_return_url", "group_chat_id"]
SECRET_KEYS = ["payme_key", "payme_test_key"]


@router.get("/settings")
async def settings_page(request: Request, staff: Staff = Depends(admin_required)):
    data = await settings.all_settings()
    async with session_scope() as s:
        hol = (await s.execute(select(Holiday).order_by(Holiday.day))).scalars().all()
        usage_rows = (await s.execute(select(AiUsage).order_by(AiUsage.day.desc()).limit(31))).scalars().all()
    key = await ai.api_key()
    masked = (key[:6] + "…" + key[-4:]) if key else ""
    today_usage = await ai.usage_today()
    cost = await ai.estimate_cost(today_usage.input_tokens, today_usage.output_tokens)
    usage = [{"day": u.day, "requests": u.requests, "inp": u.input_tokens, "out": u.output_tokens, "errors": u.errors,
              "cost": await ai.estimate_cost(u.input_tokens, u.output_tokens)} for u in usage_rows]
    from ...services import payme

    def _mask(v: str) -> str:
        return (v[:4] + "…" + v[-4:]) if v and len(v) > 8 else ("•••" if v else "")

    return render(request, "admin/settings.html", staff, s=data, holidays=hol, masked_key=masked,
                  payme_endpoint=f"{config.PANEL_URL}/payme", payme_key_mask=_mask(data.get("payme_key") or config.PAYME_KEY),
                  payme_test_key_mask=_mask(data.get("payme_test_key") or config.PAYME_TEST_KEY),
                  payme_mid=await payme.merchant_id(), known_chats=data.get("known_chats") or {},
                  key_from_env=bool(key) and not data.get("openai_api_key"), usage=usage, today_usage=today_usage,
                  today_cost=cost, ffmpeg=media.ffmpeg_available(), weekdays=worktime.WEEKDAYS_UZ)


@router.post("/settings")
async def settings_save(request: Request, staff: Staff = Depends(admin_required)):
    form = await request.form()
    values: dict = {}
    for k in INT_KEYS:
        if k in form and str(form[k]).strip().lstrip("-").isdigit():
            values[k] = int(form[k])
    for k in FLOAT_KEYS:
        if k in form:
            try:
                values[k] = float(str(form[k]).replace(",", "."))
            except ValueError:
                pass
    for k in BOOL_KEYS:
        values[k] = k in form
    for k in STR_KEYS:
        if k in form:
            values[k] = str(form[k]).strip()
    values["days_off"] = [int(x) for x in form.getlist("days_off") if str(x).isdigit()]
    for k in SECRET_KEYS:
        v = str(form.get(k, "")).strip()
        if v:
            values[k] = v
        if form.get(f"clear_{k}"):
            values[k] = ""
    if "group_chat_id" in values and values["group_chat_id"] and not values["group_chat_id"].lstrip("-").isdigit():
        values.pop("group_chat_id")
    new_key = str(form.get("openai_api_key", "")).strip()
    if new_key:
        values["openai_api_key"] = new_key
    if form.get("clear_api_key"):
        values["openai_api_key"] = ""
    old_gid = await settings.get("group_chat_id")
    await settings.set_many(values)
    new_gid = values.get("group_chat_id")
    if new_gid and str(new_gid) != str(old_gid or ""):
        # Premium guruh o'zgardi — chatlar ro'yxatida ham belgilaymiz
        from ...models import TgChat
        from ...services import tgchats

        async with session_scope() as s:
            for x in (await s.execute(select(TgChat).where(TgChat.role == "premium"))).scalars().all():
                x.role = "unassigned"
        if await tgchats.get(int(new_gid)):
            await tgchats.set_role(int(new_gid), "premium")
    await audit.log(staff.id, "settings_edit", "settings", None, ", ".join(sorted(values.keys()))[:500])
    flash(request, "Sozlamalar saqlandi")
    return RedirectResponse("/settings", 303)


@router.post("/settings/holidays/add")
async def holiday_add(request: Request, day: str = Form(...), name: str = Form(...), staff: Staff = Depends(admin_required)):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        flash(request, "Sana noto'g'ri", "danger")
        return RedirectResponse("/settings#holidays", 303)
    async with session_scope() as s:
        if not (await s.execute(select(Holiday).where(Holiday.day == d))).scalars().first():
            s.add(Holiday(day=d, name=name.strip()))
    await worktime.reload_holidays()
    flash(request, "Bayram kuni qo'shildi")
    return RedirectResponse("/settings#holidays", 303)


@router.post("/settings/holidays/{hid}/delete")
async def holiday_delete(hid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        h = await s.get(Holiday, hid)
        if h:
            await s.delete(h)
    await worktime.reload_holidays()
    flash(request, "O'chirildi")
    return RedirectResponse("/settings#holidays", 303)


@router.post("/settings/ai-test")
async def ai_test(request: Request, staff: Staff = Depends(admin_required)):
    try:
        msg = await ai.complete([{"role": "user", "content": "Salom! Bitta qisqa jumlada javob bering: siz ishlayapsizmi?"}], max_tokens=800)
        flash(request, f"✅ AI ishlayapti: {(msg.content or '').strip()[:200]}")
    except ai.AIUnavailable:
        flash(request, "AI o'chirilgan, kalit yo'q yoki kunlik limit tugagan", "danger")
    except Exception as e:  # noqa: BLE001
        flash(request, f"❌ AI xatosi: {e}", "danger")
    return RedirectResponse("/settings#ai", 303)


# ================================================================ bot matnlari


@router.get("/texts")
async def texts_page(request: Request, staff: Staff = Depends(admin_required)):
    overrides = await settings.get("texts") or {}
    items = []
    for key, label in EDITABLE.items():
        cur = overrides.get(key) or {}
        items.append({"key": key, "label": label, "uz": cur.get("uz") or TEXTS[key]["uz"], "ru": cur.get("ru") or TEXTS[key]["ru"],
                      "changed": bool(cur)})
    return render(request, "admin/texts.html", staff, items=items)


@router.post("/texts")
async def texts_save(request: Request, staff: Staff = Depends(admin_required)):
    form = await request.form()
    overrides: dict = {}
    for key in EDITABLE:
        uz = str(form.get(f"{key}_uz", "")).strip()
        ru = str(form.get(f"{key}_ru", "")).strip()
        if form.get(f"{key}_reset"):
            continue
        entry = {}
        if uz and uz != TEXTS[key]["uz"]:
            entry["uz"] = uz
        if ru and ru != TEXTS[key]["ru"]:
            entry["ru"] = ru
        if entry:
            overrides[key] = entry
    await settings.set_value("texts", overrides)
    await audit.log(staff.id, "texts_edit", "texts", None, ", ".join(overrides.keys())[:500])
    flash(request, "Bot matnlari saqlandi")
    return RedirectResponse("/texts", 303)


# ================================================================ harakatlar jurnali


@router.get("/audit")
async def audit_page(request: Request, staff_id: str = "", action: str = "", start: str = "", end: str = "",
                     page: int = 1, staff: Staff = Depends(admin_required)):
    s0, e0 = parse_range(start, end, 30)
    r0, r1 = stats.range_utc(s0, e0)
    async with session_scope() as s:
        q = select(AuditLog).where(AuditLog.created_at >= r0, AuditLog.created_at < r1)
        if staff_id.isdigit():
            q = q.where(AuditLog.staff_id == int(staff_id))
        if action:
            q = q.where(AuditLog.action == action)
        total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        rows = (await s.execute(q.order_by(AuditLog.id.desc()).offset((page - 1) * 100).limit(100))).scalars().all()
        staff_list = (await s.execute(select(Staff).order_by(Staff.full_name))).scalars().all()
    return render(request, "admin/audit.html", staff, rows=rows, total=total, page=page, pages=max(1, math.ceil(total / 100)),
                  staff_list=staff_list, actions=audit.ACTIONS,
                  f={"staff_id": staff_id, "action": action, "start": s0.isoformat(), "end": e0.isoformat()})


# ================================================================ eksport


@router.get("/exports")
async def exports_page(request: Request, staff: Staff = Depends(admin_required)):
    today = worktime.now_local().date()
    return render(request, "admin/exports.html", staff, start=(today.replace(day=1)).isoformat(), end=today.isoformat())


EXPORTS = {
    "leads": ("Leadlar", excel.leads_xlsx),
    "chats": ("Chatlar", excel.chats_xlsx),
    "operators": ("Operatorlar statistikasi", excel.operators_xlsx),
    "audit": ("Harakatlar jurnali", excel.audit_xlsx),
    "questions": ("Foydalanuvchi savollari", excel.questions_xlsx),
    "payments": ("To'lovlar", excel.payments_xlsx),
    "subscriptions": ("Obunachilar", excel.subscriptions_xlsx),
}


@router.post("/exports/{kind}")
async def export_run(kind: str, request: Request, start: str = Form(""), end: str = Form(""), status: str = Form(""),
                     all_time: bool = Form(False), staff: Staff = Depends(admin_required)):
    if kind not in EXPORTS:
        flash(request, "Noma'lum eksport", "danger")
        return RedirectResponse(request.headers.get("referer") or "/exports", 303)
    if not staff.tg_id:
        flash(request, "Telegram akkauntingiz biriktirilmagan", "danger")
        return RedirectResponse("/exports", 303)
    s0, e0 = parse_range(start, end, 30)
    title, fn = EXPORTS[kind]
    try:
        if kind == "leads":
            path = await fn(None if all_time else s0, None if all_time else e0, status or None)
        else:
            path = await fn(s0, e0)
        period = "Barcha vaqt" if (kind == "leads" and all_time) else f"{s0.strftime('%d.%m.%Y')} — {e0.strftime('%d.%m.%Y')}"
        await excel.send_to_staff(staff.tg_id, path, f"📊 {title}\n📅 {period}")
        await audit.log(staff.id, "export", kind, None, f"{title}: {period}")
        flash(request, f"✅ «{title}» Excel fayli Telegramingizga yuborildi")
    except Exception as e:  # noqa: BLE001
        flash(request, f"Eksport xatosi: {e}", "danger")
    return RedirectResponse(request.headers.get("referer") or "/exports", 303)
