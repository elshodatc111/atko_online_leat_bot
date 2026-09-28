"""Harakatlar jurnali."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import session_scope
from ..models import AuditLog

ACTIONS: dict[str, str] = {
    "login": "Panelga kirdi",
    "logout": "Paneldan chiqdi",
    "chat_claim": "Chatni oldi",
    "chat_close": "Chatni yopdi",
    "chat_transfer": "Chatni o'tkazdi",
    "lead_status": "Lead statusini o'zgartirdi",
    "lead_edit": "Lead ma'lumotini tahrirladi",
    "lead_comment": "Izoh qoldirdi",
    "lead_delete": "Leadni o'chirdi",
    "operator_add": "Operator qo'shdi",
    "operator_edit": "Operatorni tahrirladi",
    "operator_delete": "Operatorni o'chirdi",
    "operator_joined": "Operator taklif orqali qo'shildi",
    "settings_edit": "Sozlamalarni o'zgartirdi",
    "texts_edit": "Bot matnlarini o'zgartirdi",
    "content_edit": "Kontentni tahrirladi",
    "faq_approve": "FAQ taklifini tasdiqladi",
    "faq_reject": "FAQ taklifini rad etdi",
    "faq_analyze": "FAQ tahlilini ishga tushirdi",
    "material_upload": "Material yukladi",
    "material_delete": "Materialni o'chirdi",
    "broadcast_start": "Ommaviy xabar yubordi",
    "source_add": "Manba qo'shdi",
    "source_edit": "Manbani tahrirladi",
    "export": "Excel eksport qildi",
    "online": "Onlayn holatini o'zgartirdi",
}


async def log(
    staff_id: int | None,
    action: str,
    entity: str | None = None,
    entity_id: int | None = None,
    details: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    row = AuditLog(staff_id=staff_id, action=action, entity=entity, entity_id=entity_id, details=details)
    if session is not None:
        session.add(row)
        return
    async with session_scope() as s:
        s.add(row)
