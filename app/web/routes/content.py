"""Kontent: tariflar (obuna variantlari, Zoom/Individual paketlari, namuna video) va avto-eslatmalar."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select

from ...db import session_scope
from ...models import ReminderLog, ReminderStep, Staff, Tariff
from ...services import audit, knowledge, media, settings
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
    cats = dict(knowledge.CATEGORY_LABELS)
    return render(request, "content/tariffs.html", staff, rows=rows, cats=cats, plans=plans, options=options, best=best,
                  per_lesson=tariff_svc.per_lesson,
                  payme_ok=await payme.is_configured(), sample_fid=await settings.get("sample_video_file_id"),
                  sample_cap_uz=await settings.get("sample_video_caption_uz"))


@router.post("/content/sample-video")
async def sample_video_upload(request: Request, file: UploadFile | None = File(None), caption_uz: str = Form(""),
                              staff: Staff = Depends(admin_required)):
    """Video bir marta Telegramga (adminning o'ziga) yuboriladi va file_id saqlanadi — keyin serverdan yuklanmaydi."""
    from pathlib import Path

    from aiogram.types import FSInputFile

    from ...bot.instance import get_bot

    values = {"sample_video_caption_uz": caption_uz.strip()}
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
                      desc_uz: str = Form(...), sort: int = Form(0),
                      is_active: bool = Form(False), price: str = Form("0"), price_period: str = Form(""),
                      staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(Tariff, int(id)) if id.isdigit() else None
        if x is None:
            x = Tariff()
            s.add(x)
        x.category = category if category in knowledge.CATEGORY_LABELS else "group"
        x.name_uz, x.desc_uz = name_uz.strip(), desc_uz.strip()
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
                    days: int = Form(30), price: str = Form("0"), sort: int = Form(0),
                    is_active: bool = Form(False), staff: Staff = Depends(admin_required)):
    from ...models import SubscriptionPlan

    if days <= 0:
        flash(request, "Kunlar soni 0 dan katta bo'lishi kerak", "danger")
        return back("/content/tariffs")
    async with session_scope() as s:
        p = await s.get(SubscriptionPlan, int(id)) if id.isdigit() else None
        if p is None:
            p = SubscriptionPlan(tariff_id=tariff_id, title_uz="")
            s.add(p)
        p.title_uz, p.days, p.price, p.sort, p.is_active = title_uz.strip(), days, _money(price), sort, is_active
        await audit.log(staff.id, "content_edit", "plan", p.id, f"{title_uz}: {p.price} so'm / {days} kun", session=s)
    flash(request, "Obuna varianti saqlandi")
    return back("/content/tariffs")


@router.post("/content/options/save")
async def option_save(request: Request, id: str = Form(""), tariff_id: int = Form(...), lessons: int = Form(12),
                      per_week: int = Form(3), months: int = Form(1), price: str = Form("0"), sort: int = Form(0),
                      is_active: bool = Form(False), staff: Staff = Depends(admin_required)):
    """Zoom / Individual paketlari (12 dars / 20 dars) — to'lov menejer orqali."""
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


# ================================================================ eslatmalar


@router.get("/content/reminders")
async def reminders_page(request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        rows = (await s.execute(select(ReminderStep).order_by(ReminderStep.day_offset, ReminderStep.id))).scalars().all()
        sent = dict((await s.execute(select(ReminderLog.step_id, func.count(ReminderLog.id)).where(ReminderLog.ok.is_(True))
                                     .group_by(ReminderLog.step_id))).all())
    return render(request, "content/reminders.html", staff, rows=rows, sent=sent,
                  enabled=await settings.get("reminders_enabled"),
                  hours=f"{await settings.get('reminder_hours_from')}–{await settings.get('reminder_hours_to')}")


@router.post("/content/reminders/save")
async def reminder_save(request: Request, id: str = Form(""), day_offset: int = Form(...), text_uz: str = Form(...),
                        is_active: bool = Form(False),
                        staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        x = await s.get(ReminderStep, int(id)) if id.isdigit() else None
        if x is None:
            x = ReminderStep(day_offset=day_offset, text_uz="")
            s.add(x)
        x.day_offset, x.text_uz = max(0, day_offset), text_uz.strip()
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
