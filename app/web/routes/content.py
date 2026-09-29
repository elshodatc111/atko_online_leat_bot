"""Kontent: tariflar, markaz ma'lumotlari, FAQ (AI takliflari bilan), materiallar, eslatmalar, shablonlar."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select

from ...db import session_scope
from ...models import Faq, FaqSuggestion, InfoPage, Material, ReminderLog, ReminderStep, Staff, Tariff, Template, UserQuestion
from ...services import ai, audit, knowledge, media, settings
from ...services.notify import hub
from ..deps import admin_required, flash, render

log = logging.getLogger(__name__)
router = APIRouter()


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, 303)


# ================================================================ tariflar


@router.get("/content/tariffs")
async def tariffs_page(request: Request, staff: Staff = Depends(admin_required)):
    from ...models import SubscriptionPlan
    from ...services import payme

    async with session_scope() as s:
        rows = (await s.execute(select(Tariff).order_by(Tariff.sort, Tariff.id))).scalars().all()
        plans = (await s.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.sort, SubscriptionPlan.days))).scalars().all()
    from ...services import tariffs as tariff_svc

    options = await tariff_svc.all_options(active_only=False)
    best = {}
    for tr in rows:
        bid, pct = tariff_svc.best_value([o for o in options if o.tariff_id == tr.id and o.is_active])
        if bid:
            best[bid] = pct
    cats = {k: v for k, v in knowledge.CATEGORY_LABELS.items() if k != "hybrid"}
    return render(request, "content/tariffs.html", staff, rows=rows, cats=cats, plans=plans, options=options, best=best,
                  per_lesson=tariff_svc.per_lesson,
                  payme_ok=await payme.is_configured(), sample_fid=await settings.get("sample_video_file_id"),
                  sample_cap_uz=await settings.get("sample_video_caption_uz"), sample_cap_ru=await settings.get("sample_video_caption_ru"))


@router.post("/content/sample-video")
async def sample_video_upload(request: Request, file: UploadFile | None = File(None), caption_uz: str = Form(""),
                              caption_ru: str = Form(""), staff: Staff = Depends(admin_required)):
    """Video bir marta Telegramga (adminning o'ziga) yuboriladi va file_id saqlanadi — keyin serverdan yuklanmaydi."""
    from pathlib import Path

    from aiogram.types import FSInputFile

    from ...bot.instance import get_bot

    values = {"sample_video_caption_uz": caption_uz.strip(), "sample_video_caption_ru": caption_ru.strip()}
    if file and file.filename:
        if not staff.tg_id:
            flash(request, "Telegram akkauntingiz biriktirilmagan", "danger")
            return back("/content/tariffs#sample")
        data = await file.read()
        if len(data) > media.TELEGRAM_UPLOAD_LIMIT_MB * 1024 * 1024:
            flash(request, f"Video {media.TELEGRAM_UPLOAD_LIMIT_MB} MB dan katta. Kattaroq videoni botga to'g'ridan-to'g'ri yuboring — "
                           "bot uni «Namuna video» qilib saqlashni taklif qiladi.", "danger")
            return back("/content/tariffs#sample")
        p = media.new_path(media.guess_ext(file.filename, file.content_type, ".mp4"), "tmp")
        p.write_bytes(data)
        try:
            m = await get_bot().send_video(staff.tg_id, FSInputFile(p, filename=file.filename),
                                           caption="✅ Namuna video Telegram bulutiga saqlandi")
            if not m.video:
                raise ValueError("Telegram videoni qabul qilmadi (mp4 formatda yuklang)")
            values["sample_video_file_id"] = m.video.file_id
        except Exception as e:  # noqa: BLE001
            flash(request, f"Videoni yuklab bo'lmadi: {e}", "danger")
            return back("/content/tariffs#sample")
        finally:
            Path(p).unlink(missing_ok=True)
    await settings.set_many(values)
    await audit.log(staff.id, "content_edit", "sample_video", None, "Namuna video")
    flash(request, "Namuna video saqlandi" if file and file.filename else "Saqlandi")
    return back("/content/tariffs#sample")


@router.post("/content/sample-video/delete")
async def sample_video_delete(request: Request, staff: Staff = Depends(admin_required)):
    await settings.set_value("sample_video_file_id", "")
    flash(request, "Namuna video o'chirildi")
    return back("/content/tariffs#sample")


@router.post("/content/sample-video/preview")
async def sample_video_preview(request: Request, staff: Staff = Depends(admin_required)):
    from ...bot.instance import get_bot

    fid = await settings.get("sample_video_file_id")
    try:
        await get_bot().send_video(staff.tg_id, fid, caption="👀 Namuna video (ko'rib chiqish)")
        flash(request, "Video Telegramingizga yuborildi")
    except Exception as e:  # noqa: BLE001
        flash(request, f"Xatolik: {e}", "danger")
    return back("/content/tariffs#sample")


@router.post("/content/tariffs/save")
async def tariff_save(request: Request, id: str = Form(""), category: str = Form("group"), name_uz: str = Form(...),
                      name_ru: str = Form(...), desc_uz: str = Form(...), desc_ru: str = Form(...), sort: int = Form(0),
                      is_active: bool = Form(False), price: str = Form("0"), price_period: str = Form(""),
                      staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(Tariff, int(id)) if id.isdigit() else None
        if x is None:
            x = Tariff()
            s.add(x)
        x.category = category if category in knowledge.CATEGORY_LABELS else "group"
        x.name_uz, x.name_ru, x.desc_uz, x.desc_ru = name_uz.strip(), name_ru.strip(), desc_uz.strip(), desc_ru.strip()
        x.sort, x.is_active = sort, is_active
        x.is_subscription = x.category == "subscription"
        x.price = _money(price)
        x.price_period = price_period.strip()[:32]
        await audit.log(staff.id, "content_edit", "tariff", x.id, f"{name_uz}: {x.price} so'm", session=s)
    flash(request, "Tarif saqlandi")
    return back("/content/tariffs")


def _money(raw: str) -> int:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return int(digits) if digits else 0


@router.post("/content/plans/save")
async def plan_save(request: Request, id: str = Form(""), tariff_id: int = Form(...), title_uz: str = Form(...),
                    title_ru: str = Form(...), days: int = Form(30), price: str = Form("0"), sort: int = Form(0),
                    is_active: bool = Form(False), staff: Staff = Depends(admin_required)):
    from ...models import SubscriptionPlan

    if days <= 0:
        flash(request, "Kunlar soni 0 dan katta bo'lishi kerak", "danger")
        return back("/content/tariffs")
    async with session_scope() as s:
        p = await s.get(SubscriptionPlan, int(id)) if id.isdigit() else None
        if p is None:
            p = SubscriptionPlan(tariff_id=tariff_id, title_uz="", title_ru="")
            s.add(p)
        p.title_uz, p.title_ru, p.days, p.price, p.sort, p.is_active = title_uz.strip(), title_ru.strip(), days, _money(price), sort, is_active
        await audit.log(staff.id, "content_edit", "plan", p.id, f"{title_uz}: {p.price} so'm / {days} kun", session=s)
    flash(request, "Obuna varianti saqlandi")
    return back("/content/tariffs")


@router.post("/content/options/save")
async def option_save(request: Request, id: str = Form(""), tariff_id: int = Form(...), lessons: int = Form(12),
                      per_week: int = Form(3), months: int = Form(1), price: str = Form("0"), sort: int = Form(0),
                      is_active: bool = Form(False), staff: Staff = Depends(admin_required)):
    """Zoom / Individual paketlari (12 dars / 20 dars) — to'lov admin orqali."""
    from ...models import TariffOption

    if lessons <= 0 or per_week < 0 or months <= 0:
        flash(request, "Darslar soni va davomiylik 0 dan katta bo'lishi kerak", "danger")
        return back("/content/tariffs")
    async with session_scope() as s:
        tr = await s.get(Tariff, tariff_id)
        if not tr or tr.is_subscription:
            flash(request, "Paketlar faqat Zoom / Individual (obuna bo'lmagan) tariflar uchun", "danger")
            return back("/content/tariffs")
        o = await s.get(TariffOption, int(id)) if id.isdigit() else None
        if o is None:
            o = TariffOption(tariff_id=tariff_id)
            s.add(o)
        o.lessons, o.per_week, o.months, o.price, o.sort, o.is_active = lessons, per_week, months, _money(price), sort, is_active
        await audit.log(staff.id, "content_edit", "tariff_option", o.id, f"{tr.name_uz}: {lessons} dars — {o.price} so'm", session=s)
    flash(request, "Paket saqlandi")
    return back("/content/tariffs")


@router.post("/content/options/{oid}/delete")
async def option_delete(oid: int, request: Request, staff: Staff = Depends(admin_required)):
    from ...models import TariffOption

    async with session_scope() as s:
        o = await s.get(TariffOption, oid)
        if o:
            await s.delete(o)
            await audit.log(staff.id, "content_edit", "tariff_option", oid, "Paket o'chirildi", session=s)
    flash(request, "Paket o'chirildi")
    return back("/content/tariffs")


@router.post("/content/plans/{pid}/delete")
async def plan_delete(pid: int, request: Request, staff: Staff = Depends(admin_required)):
    from ...models import SubscriptionPlan

    async with session_scope() as s:
        p = await s.get(SubscriptionPlan, pid)
        if p:
            await s.delete(p)
    flash(request, "O'chirildi")
    return back("/content/tariffs")


@router.post("/content/tariffs/{tid}/delete")
async def tariff_delete(tid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(Tariff, tid)
        if x:
            await s.delete(x)
            await audit.log(staff.id, "content_edit", "tariff", tid, f"O'chirildi: {x.name_uz}", session=s)
    flash(request, "Tarif o'chirildi")
    return back("/content/tariffs")


# ================================================================ markaz ma'lumotlari


@router.get("/content/info")
async def info_page(request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        rows = (await s.execute(select(InfoPage).order_by(InfoPage.sort, InfoPage.id))).scalars().all()
    return render(request, "content/info.html", staff, rows=rows)


@router.post("/content/info/save")
async def info_save(request: Request, id: str = Form(""), key: str = Form(""), title_uz: str = Form(...),
                    title_ru: str = Form(...), body_uz: str = Form(...), body_ru: str = Form(...), sort: int = Form(0),
                    show_in_menu: bool = Form(False), staff: Staff = Depends(admin_required)):
    import re
    import secrets

    async with session_scope() as s:
        x = await s.get(InfoPage, int(id)) if id.isdigit() else None
        if x is None:
            x = InfoPage(key=re.sub(r"[^a-z0-9_]", "", key.lower())[:32] or f"page_{secrets.token_hex(3)}")
            s.add(x)
        x.title_uz, x.title_ru, x.body_uz, x.body_ru = title_uz.strip(), title_ru.strip(), body_uz.strip(), body_ru.strip()
        x.sort, x.show_in_menu = sort, show_in_menu
        await audit.log(staff.id, "content_edit", "info", x.id, title_uz, session=s)
    flash(request, "Saqlandi")
    return back("/content/info")


@router.post("/content/info/{pid}/delete")
async def info_delete(pid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(InfoPage, pid)
        if x:
            await s.delete(x)
    flash(request, "O'chirildi")
    return back("/content/info")


# ================================================================ FAQ


@router.get("/faq")
async def faq_page(request: Request, tab: str = "suggestions", staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        suggestions = (await s.execute(select(FaqSuggestion).where(FaqSuggestion.status == "pending")
                                       .order_by(FaqSuggestion.count.desc(), FaqSuggestion.id.desc()))).scalars().all()
        faqs = (await s.execute(select(Faq).order_by(Faq.sort, Faq.asked_count.desc(), Faq.id))).scalars().all()
        unanswered = (await s.execute(select(UserQuestion).where(UserQuestion.answered.is_(False))
                                      .order_by(UserQuestion.id.desc()).limit(200))).scalars().all()
        recent = (await s.execute(select(UserQuestion).order_by(UserQuestion.id.desc()).limit(200))).scalars().all()
        pending_q = (await s.execute(select(func.count(UserQuestion.id)).where(UserQuestion.processed.is_(False)))).scalar_one()
        history = (await s.execute(select(FaqSuggestion).where(FaqSuggestion.status != "pending")
                                   .order_by(FaqSuggestion.updated_at.desc()).limit(50))).scalars().all()
    return render(request, "content/faq.html", staff, tab=tab, suggestions=suggestions, faqs=faqs, unanswered=unanswered,
                  recent=recent, pending_q=pending_q, history=history, last_run=await settings.get("faq_last_run"),
                  min_count=int(await settings.get("faq_min_count") or 1))


async def _analyze_bg(staff_id: int) -> None:
    try:
        res = await ai.analyze_questions()
        await hub.emit("alert", {"level": "success", "text": f"FAQ tahlili tugadi: {res['processed']} savol, {res['created']} yangi, {res['updated']} yangilangan taklif"},
                       staff_ids={staff_id})
    except ai.AIUnavailable:
        await hub.emit("alert", {"level": "danger", "text": "AI mavjud emas (o'chirilgan yoki limit tugagan)"}, staff_ids={staff_id})
    except Exception as e:  # noqa: BLE001
        log.exception("FAQ tahlil xatosi")
        await hub.emit("alert", {"level": "danger", "text": f"FAQ tahlil xatosi: {e}"}, staff_ids={staff_id})


@router.post("/faq/analyze")
async def faq_analyze(request: Request, staff: Staff = Depends(admin_required)):
    asyncio.create_task(_analyze_bg(staff.id))
    await audit.log(staff.id, "faq_analyze")
    flash(request, "AI tahlili boshlandi. Tugagach panelda xabar chiqadi — sahifani yangilang.", "info")
    return back("/faq")


@router.post("/faq/suggestions/{sid}/approve")
async def suggestion_approve(sid: int, request: Request, q_uz: str = Form(...), q_ru: str = Form(...), a_uz: str = Form(...),
                             a_ru: str = Form(...), staff: Staff = Depends(admin_required)):
    if "[Admin to'ldirsin]" in a_uz or "[Admin to'ldirsin]" in a_ru:
        flash(request, "Avval javobdagi «[Admin to'ldirsin]» joyini to'ldiring", "danger")
        return back("/faq")
    async with session_scope() as s:
        sug = await s.get(FaqSuggestion, sid)
        if not sug:
            return back("/faq")
        sug.status = "approved"
        sug.q_uz, sug.q_ru, sug.a_uz, sug.a_ru = q_uz, q_ru, a_uz, a_ru
        s.add(Faq(q_uz=q_uz.strip(), q_ru=q_ru.strip(), a_uz=a_uz.strip(), a_ru=a_ru.strip(), origin="ai", asked_count=sug.count))
        await audit.log(staff.id, "faq_approve", "faq_suggestion", sid, q_uz[:200], session=s)
    flash(request, "✅ Savol FAQ ro'yxatiga qo'shildi — botda darhol ko'rinadi")
    return back("/faq")


@router.post("/faq/suggestions/{sid}/reject")
async def suggestion_reject(sid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        sug = await s.get(FaqSuggestion, sid)
        if sug:
            sug.status = "rejected"
            await audit.log(staff.id, "faq_reject", "faq_suggestion", sid, sug.question[:200], session=s)
    flash(request, "Taklif rad etildi")
    return back("/faq")


@router.post("/faq/save")
async def faq_save(request: Request, id: str = Form(""), q_uz: str = Form(...), q_ru: str = Form(...), a_uz: str = Form(...),
                   a_ru: str = Form(...), sort: int = Form(0), is_active: bool = Form(False),
                   staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        f = await s.get(Faq, int(id)) if id.isdigit() else None
        if f is None:
            f = Faq(origin="manual")
            s.add(f)
        f.q_uz, f.q_ru, f.a_uz, f.a_ru, f.sort, f.is_active = q_uz.strip(), q_ru.strip(), a_uz.strip(), a_ru.strip(), sort, is_active
        await audit.log(staff.id, "content_edit", "faq", f.id, q_uz[:200], session=s)
    flash(request, "FAQ saqlandi")
    return back("/faq?tab=faq")


@router.post("/faq/{fid}/delete")
async def faq_delete(fid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        f = await s.get(Faq, fid)
        if f:
            await s.delete(f)
    flash(request, "O'chirildi")
    return back("/faq?tab=faq")


@router.post("/faq/translate")
async def faq_translate(text: str = Form(...), target: str = Form("ru"), staff: Staff = Depends(admin_required)):
    try:
        return {"ok": True, "text": await ai.translate(text, target)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ================================================================ eslatmalar


@router.get("/content/reminders")
async def reminders_page(request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        rows = (await s.execute(select(ReminderStep).order_by(ReminderStep.day_offset, ReminderStep.id))).scalars().all()
        mats = (await s.execute(select(Material).order_by(Material.title))).scalars().all()
        sent = dict((await s.execute(select(ReminderLog.step_id, func.count(ReminderLog.id)).where(ReminderLog.ok.is_(True))
                                     .group_by(ReminderLog.step_id))).all())
    return render(request, "content/reminders.html", staff, rows=rows, mats=mats, sent=sent,
                  enabled=await settings.get("reminders_enabled"),
                  hours=f"{await settings.get('reminder_hours_from')}–{await settings.get('reminder_hours_to')}")


@router.post("/content/reminders/save")
async def reminder_save(request: Request, id: str = Form(""), day_offset: int = Form(...), text_uz: str = Form(...),
                        text_ru: str = Form(...), material_id: str = Form(""), is_active: bool = Form(False),
                        staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(ReminderStep, int(id)) if id.isdigit() else None
        if x is None:
            x = ReminderStep(day_offset=day_offset, text_uz="", text_ru="")
            s.add(x)
        x.day_offset, x.text_uz, x.text_ru = max(0, day_offset), text_uz.strip(), text_ru.strip()
        x.material_id = int(material_id) if material_id.isdigit() else None
        x.is_active = is_active
        await audit.log(staff.id, "content_edit", "reminder", x.id, f"{day_offset}-kun", session=s)
    flash(request, "Eslatma saqlandi")
    return back("/content/reminders")


@router.post("/content/reminders/{rid}/delete")
async def reminder_delete(rid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        await s.execute(delete(ReminderStep).where(ReminderStep.id == rid))
    flash(request, "O'chirildi")
    return back("/content/reminders")


# ================================================================ shablonlar


@router.get("/content/templates")
async def templates_page(request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        rows = (await s.execute(select(Template).order_by(Template.sort, Template.id))).scalars().all()
    return render(request, "content/templates.html", staff, rows=rows)


@router.post("/content/templates/save")
async def template_save(request: Request, id: str = Form(""), title: str = Form(...), text_uz: str = Form(...),
                        text_ru: str = Form(...), sort: int = Form(0), staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(Template, int(id)) if id.isdigit() else None
        if x is None:
            x = Template(title="", text_uz="", text_ru="")
            s.add(x)
        x.title, x.text_uz, x.text_ru, x.sort = title.strip(), text_uz.strip(), text_ru.strip(), sort
    flash(request, "Shablon saqlandi")
    return back("/content/templates")


@router.post("/content/templates/{tid}/delete")
async def template_delete(tid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        await s.execute(delete(Template).where(Template.id == tid))
    flash(request, "O'chirildi")
    return back("/content/templates")
