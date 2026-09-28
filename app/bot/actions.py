"""Bot harakatlari: operatorga ulanish, bepul dars, material yuborish."""
from __future__ import annotations

import html

from aiogram.types import FSInputFile, InlineKeyboardMarkup
from sqlalchemy import select

from ..db import session_scope
from ..models import Chat, Lead, Material
from ..services import chats as chat_svc
from ..services import worktime
from ..services.notify import hub
from .common import send_menu, update_lead
from .instance import get_bot
from .keyboards import contact_kb
from .texts import t


async def require_phone(lead: Lead, pending: str, ref: int | None = None) -> bool:
    """Telefon yo'q bo'lsa so'raydi va keyingi harakatni eslab qoladi. True — telefon bor."""
    if lead.phone:
        return True
    await update_lead(lead.id, pending_input=pending, pending_ref=ref)
    await get_bot().send_message(lead.tg_id, t("phone_needed", lead.lang), reply_markup=contact_kb(lead.lang, allow_later=False))
    return False


async def operator_request(lead: Lead, reason: str = "user", note: str | None = None, silent_ok: bool = False) -> None:
    bot = get_bot()
    async with session_scope() as s:
        existing = await chat_svc.active_chat(s, lead.id)
        op_name = existing.operator.display_name if existing and existing.operator else None
        existing_status = existing.status if existing else None
    if existing_status == "waiting":
        if not silent_ok:
            await bot.send_message(lead.tg_id, t("already_waiting", lead.lang))
        return
    if existing_status == "active":
        await bot.send_message(lead.tg_id, t("already_active", lead.lang, operator=html.escape(op_name or "")))
        return
    chat, created, off_hours = await chat_svc.request_operator(lead.id, reason=reason, note=note)
    if silent_ok:
        return
    if off_hours:
        nxt = await worktime.next_opening()
        text = t("operator_off_hours", lead.lang, hours=await worktime.work_hours_text(),
                 next_open=nxt.strftime("%d.%m.%Y %H:%M"))
    else:
        text = t("operator_wait", lead.lang)
    await bot.send_message(lead.tg_id, text)


async def trial_request(lead: Lead) -> None:
    lead = await update_lead(lead.id, trial_requested=True)
    await get_bot().send_message(lead.tg_id, t("trial_ok", lead.lang))
    await operator_request(lead, reason="trial", silent_ok=True)
    await hub.emit("alert", {"level": "info", "text": f"🎁 {lead.display} bepul darsga yozilmoqchi"})


async def send_material(lead: Lead, material_id: int) -> None:
    bot = get_bot()
    async with session_scope() as s:
        m = await s.get(Material, material_id)
        if not m or not m.is_free:
            return
        file_id, path, name, title = m.tg_file_id, m.file_path, m.file_name, m.title
    doc = file_id or FSInputFile(path, filename=name)
    sent = await bot.send_document(lead.tg_id, doc, caption=f"📄 {html.escape(title)}")
    async with session_scope() as s:
        m = await s.get(Material, material_id)
        m.downloads = (m.downloads or 0) + 1
        if not m.tg_file_id and sent.document:
            m.tg_file_id = sent.document.file_id
    await chat_svc.add_message(lead.id, "bot", text=f"[Material yuborildi: {title}]", emit=False)


async def run_pending_after_phone(lead: Lead) -> bool:
    """Telefon olingandan keyin kutilgan harakatni bajaradi."""
    pending, ref = lead.pending_input, lead.pending_ref
    if not pending or not pending.startswith("after_phone"):
        return False
    lead = await update_lead(lead.id, pending_input=None, pending_ref=None)
    await send_menu(lead.tg_id, lead, t("phone_saved", lead.lang, phone=lead.phone))
    if pending == "after_phone_operator":
        await operator_request(lead)
    elif pending == "after_phone_trial":
        await trial_request(lead)
    elif pending == "after_phone_material" and ref:
        await send_material(lead, ref)
    return True
