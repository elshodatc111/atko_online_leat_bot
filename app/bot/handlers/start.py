"""/start, til tanlash, ro'yxatdan o'tish (ism → telefon → maqsad → format), xodim login/taklif."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.types import Message as TgMessage
from sqlalchemy import select

from ...config import config
from ...db import session_scope, utcnow
from ...models import LoginToken, Staff
from ...services import audit
from ...services.notify import hub
from ..actions import run_pending_after_phone
from ..common import esc, get_lead, get_or_create_lead, normalize_phone, send_menu, update_lead
from ..keyboards import contact_kb, format_kb, goal_kb, ib, lang_kb
from ..texts import t

router = Router(name="start")
router.message.filter(F.chat.type == "private")  # o'quv guruhlarida /start va boshqalar ishlamaydi


# ------------------------------------------------------------------ xodimlar


async def _staff_by_tg(tg_id: int) -> Staff | None:
    async with session_scope() as s:
        return (await s.execute(select(Staff).where(Staff.tg_id == tg_id, Staff.is_active.is_(True)))).scalars().first()


async def _handle_login(msg: TgMessage, token: str) -> None:
    staff = await _staff_by_tg(msg.from_user.id)
    if not staff:
        await msg.answer("⛔️ Siz ATKO panelining xodimi sifatida ro'yxatdan o'tmagansiz.\n"
                         f"Telegram ID: <code>{msg.from_user.id}</code> — uni adminga yuboring.")
        return
    async with session_scope() as s:
        lt = await s.get(LoginToken, token)
        if not lt or lt.status != "pending":
            await msg.answer("⚠️ Kirish havolasi eskirgan. Panelda qaytadan «Telegram orqali kirish» tugmasini bosing.")
            return
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib("✅ Kirishni tasdiqlash", f"login_ok:{token}")],
                                               [ib("❌ Bu men emasman", f"login_no:{token}")]])
    await msg.answer(f"🔐 <b>ATKO panelga kirish</b>\n\n{esc(staff.full_name)}, panelga kirishni tasdiqlaysizmi?", reply_markup=kb)


@router.callback_query(F.data.startswith("login_ok:"))
async def login_ok(cb: CallbackQuery) -> None:
    token = cb.data.split(":", 1)[1]
    staff = await _staff_by_tg(cb.from_user.id)
    if not staff:
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    async with session_scope() as s:
        lt = await s.get(LoginToken, token)
        if not lt or lt.status != "pending":
            await cb.answer("Havola eskirgan", show_alert=True)
            return
        lt.staff_id = staff.id
        lt.status = "confirmed"
        staff_obj = await s.get(Staff, staff.id)
        staff_obj.tg_username = cb.from_user.username
    await cb.message.edit_text("✅ Kirish tasdiqlandi! Brauzerga qayting — panel avtomatik ochiladi.")
    await cb.answer()


@router.callback_query(F.data.startswith("login_no:"))
async def login_no(cb: CallbackQuery) -> None:
    token = cb.data.split(":", 1)[1]
    async with session_scope() as s:
        lt = await s.get(LoginToken, token)
        if lt:
            lt.status = "rejected"
    await cb.message.edit_text("❌ Kirish rad etildi.")
    await cb.answer()


async def _handle_invite(msg: TgMessage, token: str) -> None:
    async with session_scope() as s:
        st = (await s.execute(select(Staff).where(Staff.invite_token == token))).scalars().first()
        if not st or (st.invite_expires and st.invite_expires < utcnow()):
            await msg.answer("⚠️ Taklif havolasi yaroqsiz yoki muddati o'tgan. Admindan yangi havola so'rang.")
            return
        other = (await s.execute(select(Staff).where(Staff.tg_id == msg.from_user.id, Staff.id != st.id))).scalars().first()
        if other:
            await msg.answer("⚠️ Bu Telegram akkaunt allaqachon boshqa xodimga biriktirilgan.")
            return
        st.tg_id = msg.from_user.id
        st.tg_username = msg.from_user.username
        st.invite_token = None
        st.invite_expires = None
        st.is_active = True
        name, role, sid = st.full_name, st.role, st.id
        await audit.log(sid, "operator_joined", "staff", sid, f"@{msg.from_user.username or msg.from_user.id}", session=s)
    await hub.emit("alert", {"level": "success", "text": f"{name} panelga qo'shildi"}, admins_only=True)
    await msg.answer(
        f"🎉 Tabriklaymiz, {esc(name)}! Siz ATKO panelida <b>{'admin' if role == 'admin' else 'operator'}</b> sifatida ro'yxatdan o'tdingiz.\n\n"
        f"🖥 Panel: {config.PANEL_URL}\n🔐 Kirish: saytda Telegram ID ingizni kiriting — <code>{msg.from_user.id}</code>, "
        "bot sizga tasdiqlash kodini yuboradi.\n\n"
        "Yangi murojaatlar haqida shu bot orqali xabar olasiz.",
        reply_markup=ReplyKeyboardRemove(),
    )


_last_admin_video: dict[int, str] = {}


@router.message(F.video, F.chat.type == "private")
async def admin_video(msg: TgMessage) -> None:
    """Admin botga video yuborsa — uni «Namuna video» sifatida saqlash taklif qilinadi (Telegram bulutida, file_id)."""
    staff = await _staff_by_tg(msg.from_user.id)
    if not staff or staff.role != "admin":
        from aiogram.dispatcher.event.bases import SkipHandler

        raise SkipHandler()
    _last_admin_video[msg.from_user.id] = msg.video.file_id
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib("✅ Namuna video sifatida saqlash", "setsample")],
                                               [ib("✖️ Yo'q", "setsample_no")]])
    await msg.answer("🎬 Bu videoni obuna oynasidagi <b>«Namuna darsni ko'rish»</b> videosi qilib saqlaymi?\n"
                     "Video Telegram bulutida qoladi — serverdan qayta yuklanmaydi.", reply_markup=kb)


@router.callback_query(F.data.in_({"setsample", "setsample_no"}))
async def admin_video_save(cb: CallbackQuery) -> None:
    from ...services import settings as st

    staff = await _staff_by_tg(cb.from_user.id)
    fid = _last_admin_video.pop(cb.from_user.id, None)
    if cb.data == "setsample_no" or not staff or staff.role != "admin":
        await cb.message.edit_text("Bekor qilindi.")
        await cb.answer()
        return
    if not fid:
        await cb.answer("Video topilmadi, qayta yuboring", show_alert=True)
        return
    await st.set_value("sample_video_file_id", fid)
    await audit.log(staff.id, "content_edit", "sample_video", None, "Namuna video (bot orqali)")
    await cb.message.edit_text("✅ Namuna video saqlandi! Endi obuna oynasida «🎬 Namuna darsni ko'rish» tugmasi chiqadi.")
    await cb.answer()


@router.message(Command("myid"))
async def my_id(msg: TgMessage) -> None:
    await msg.answer(f"Telegram ID: <code>{msg.from_user.id}</code>")


@router.message(Command("panel"))
async def panel_cmd(msg: TgMessage) -> None:
    if await _staff_by_tg(msg.from_user.id):
        await msg.answer(f"🖥 Panel: {config.PANEL_URL}")


# ------------------------------------------------------------------ leadlar


@router.message(CommandStart())
async def start(msg: TgMessage, command: CommandObject) -> None:
    payload = (command.args or "").strip()
    if payload.startswith("login_"):
        await _handle_login(msg, payload[6:])
        return
    if payload.startswith("inv_"):
        await _handle_invite(msg, payload[4:])
        return
    lead, created = await get_or_create_lead(msg.from_user, payload or None)
    if created or lead.onboarding_step == "lang":
        await update_lead(lead.id, onboarding_step="lang")
        await msg.answer(t("choose_lang", lead.lang), reply_markup=lang_kb())
        return
    if not lead.phone:
        await update_lead(lead.id, onboarding_step="phone" if lead.onboarding_step in (None, "phone") else lead.onboarding_step)
        await msg.answer(t("welcome", lead.lang))
        await msg.answer(t("phone_required", lead.lang), reply_markup=contact_kb(lead.lang))
        return
    await send_menu(msg.chat.id, lead, t("welcome", lead.lang))


@router.callback_query(F.data.startswith("lang:"))
async def choose_lang(cb: CallbackQuery) -> None:
    lang = cb.data.split(":", 1)[1]
    lead = await get_lead(cb.from_user.id)
    if not lead:
        lead, _ = await get_or_create_lead(cb.from_user)
    onboarding = lead.onboarding_step == "lang"
    lead = await update_lead(lead.id, lang=lang, onboarding_step="name" if onboarding else lead.onboarding_step)
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
    if onboarding:
        await cb.message.answer(t("welcome", lang))
        await cb.message.answer(t("ask_name", lang), reply_markup=ReplyKeyboardRemove())
    else:
        await send_menu(cb.from_user.id, lead, t("lang_changed", lang))


async def ask_phone(lead) -> None:
    from ..instance import get_bot

    await get_bot().send_message(lead.tg_id, t("ask_phone", lead.lang, name=esc(lead.name or "")),
                                 reply_markup=contact_kb(lead.lang))


async def ask_goal(lead) -> None:
    from ..instance import get_bot

    lead = await update_lead(lead.id, onboarding_step="goal")
    await get_bot().send_message(lead.tg_id, t("ask_goal", lead.lang), reply_markup=goal_kb(lead.lang))


@router.message(F.contact)
async def got_contact(msg: TgMessage) -> None:
    lead = await get_lead(msg.from_user.id)
    if not lead:
        lead, _ = await get_or_create_lead(msg.from_user)
    if msg.contact.user_id != msg.from_user.id:
        await msg.answer(t("phone_own_only", lead.lang), reply_markup=contact_kb(lead.lang))
        return
    phone = normalize_phone(msg.contact.phone_number) or ("+" + msg.contact.phone_number.lstrip("+"))
    lead = await update_lead(lead.id, phone=phone)
    await hub.emit("lead_updated", {"lead_id": lead.id, "phone": phone})
    if lead.onboarding_step == "phone":
        await msg.answer(t("phone_saved", lead.lang, phone=phone), reply_markup=ReplyKeyboardRemove())
        if lead.goal and lead.study_format:
            lead = await update_lead(lead.id, onboarding_step=None)
            await send_menu(msg.chat.id, lead, t("onboarding_done", lead.lang))
        else:
            await ask_goal(lead)
        return
    if await run_pending_after_phone(lead):
        return
    await send_menu(msg.chat.id, lead, t("phone_saved", lead.lang, phone=phone))


@router.callback_query(F.data.startswith("goal:"))
async def choose_goal(cb: CallbackQuery) -> None:
    val = cb.data.split(":", 1)[1]
    lead = await get_lead(cb.from_user.id)
    if not lead:
        await cb.answer()
        return
    upd = {"onboarding_step": "format" if lead.onboarding_step == "goal" else lead.onboarding_step}
    if val != "skip":
        upd["goal"] = val
    lead = await update_lead(lead.id, **upd)
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    if lead.onboarding_step == "format":
        await cb.message.answer(t("ask_format", lead.lang), reply_markup=format_kb(lead.lang))


@router.callback_query(F.data.startswith("fmt:"))
async def choose_format(cb: CallbackQuery) -> None:
    val = cb.data.split(":", 1)[1]
    lead = await get_lead(cb.from_user.id)
    if not lead:
        await cb.answer()
        return
    upd: dict = {"onboarding_step": None}
    if val != "skip":
        upd["study_format"] = val
    lead = await update_lead(lead.id, **upd)
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await send_menu(cb.from_user.id, lead, t("onboarding_done", lead.lang))


async def handle_onboarding_text(msg: TgMessage, lead) -> bool:
    """Ro'yxatdan o'tish bosqichidagi matnli javoblar. True — xabar qayta ishlangan."""
    step = lead.onboarding_step
    text = (msg.text or "").strip()
    if step == "lang":
        await msg.answer(t("choose_lang", lead.lang), reply_markup=lang_kb())
        return True
    if step == "name":
        if not text or text.startswith("/"):
            await msg.answer(t("ask_name", lead.lang))
            return True
        lead = await update_lead(lead.id, name=text[:64], onboarding_step="phone")
        await hub.emit("lead_updated", {"lead_id": lead.id})
        await ask_phone(lead)
        return True
    if step == "phone":
        # telefon faqat «📱 Raqamni yuborish» tugmasi orqali qabul qilinadi
        await msg.answer(t("phone_required", lead.lang), reply_markup=contact_kb(lead.lang))
        return True
    if step in ("goal", "format"):
        # tugma o'rniga savol yozdi — ro'yxatdan o'tishni yakunlab, savolni qayta ishlaymiz
        lead = await update_lead(lead.id, onboarding_step=None)
        await send_menu(msg.chat.id, lead, t("onboarding_done", lead.lang))
        return False
    return False
