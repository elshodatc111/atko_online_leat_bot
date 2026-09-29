"""Telegram: asosiy kanalni rivojlantirish (tahlil + AI g'oyalar) va o'quv guruhlari (a'zolar soni, postlar).
Barcha bo'limlar faqat admin uchun."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ...db import session_scope, utcnow
from ...models import CHAT_ROLES, POST_STATUSES, ChannelInsight, GroupPost, Staff, TgChat
from ...services import audit, channel, group_posts, media, settings, tgchats, worktime
from ..deps import admin_required, flash, render

log = logging.getLogger(__name__)
router = APIRouter()

IMPORT_LIMIT_MB = 50
PHOTO_LIMIT_MB = 10


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, 303)


# ================================================================ asosiy kanal


@router.get("/channel")
async def channel_page(request: Request, insight: int | None = None, days: int = 30, staff: Staff = Depends(admin_required)):
    ch = await tgchats.main_channel()
    ctx: dict = {"ch": ch, "days": days if days in (7, 30, 90) else 30, "kind_labels": channel.KIND_LABELS,
                 "weekdays": channel.WEEKDAYS, "channel_username": await settings.get("channel_username") or "",
                 "ai_enabled": await settings.get("channel_ai_enabled"), "ai_hour": await settings.get("channel_ai_hour"),
                 "pct": channel._rate}
    if ch:
        st = await channel.stats(ch.chat_id, ctx["days"])
        async with session_scope() as s:
            history = (await s.execute(select(ChannelInsight).where(ChannelInsight.chat_id == ch.chat_id)
                                       .order_by(ChannelInsight.id.desc()).limit(30))).scalars().all()
            cur = await s.get(ChannelInsight, insight) if insight else None
        cur = cur or next((h for h in history if h.data), None)
        failed = next((h for h in history if h.error), None)
        chart = {"labels": [r.day.strftime("%d.%m") for r in st["hist"]], "members": [r.members for r in st["hist"]],
                 "joined": [r.joined for r in st["hist"]], "left": [-r.left for r in st["hist"]]}
        async with session_scope() as s:
            cposts = (await s.execute(select(GroupPost).where(GroupPost.dest == "channel")
                                      .order_by(GroupPost.id.desc()).limit(30))).scalars().all()
        scheduled_notes = {p.note for p in cposts if p.note and p.status in ("scheduled", "sent", "draft")}
        ctx.update(st=st, chart=chart, history=history, cur=cur, cposts=cposts, scheduled_notes=scheduled_notes,
                   default_time=(worktime.now_local() + timedelta(hours=1)).replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M"),
                   last_error=failed if failed and (not cur or failed.id > cur.id) else None)
    return render(request, "growth/channel.html", staff, **ctx)


@router.post("/channel/connect")
async def channel_connect(request: Request, ref: str = Form(...), staff: Staff = Depends(admin_required)):
    ref = ref.strip()
    if ref.startswith("https://t.me/"):
        ref = ref.rsplit("/", 1)[-1]
    target: int | str = int(ref) if ref.lstrip("-").isdigit() else "@" + ref.lstrip("@")
    try:
        x = await tgchats.register(target)
    except Exception as e:  # noqa: BLE001
        flash(request, f"Kanalni topib bo'lmadi: {e}. Botni kanalga admin qilib qo'shganingizni tekshiring.", "danger")
        return back("/channel")
    if not x or x.type != "channel":
        flash(request, "Bu kanal emas", "danger")
        return back("/channel")
    if x.bot_status != "administrator":
        flash(request, "Bot kanalda admin emas — avval botni kanalga admin qilib qo'shing", "danger")
        return back("/channel")
    await tgchats.set_role(x.chat_id, "channel")
    await audit.log(staff.id, "channel", "channel", x.chat_id, f"Asosiy kanal: {x.title}")
    flash(request, f"✅ Asosiy kanal ulandi: {x.title}")
    return back("/channel")


@router.post("/channel/refresh")
async def channel_refresh(request: Request, staff: Staff = Depends(admin_required)):
    ch = await tgchats.main_channel()
    if ch:
        await tgchats.refresh(ch.chat_id)
    flash(request, "Yangilandi")
    return back("/channel")


@router.post("/channel/ideas")
async def channel_ideas(request: Request, staff: Staff = Depends(admin_required)):
    ins = await channel.generate_ideas("manual", staff.id)
    if ins is None:
        flash(request, "Asosiy kanal ulanmagan", "danger")
    elif ins.error:
        flash(request, f"AI g'oyalarni tayyorlay olmadi: {ins.error}", "danger")
    else:
        flash(request, "✅ Yangi tahlil va g'oyalar tayyor")
        return back(f"/channel?insight={ins.id}")
    return back("/channel")


@router.post("/channel/settings")
async def channel_settings(request: Request, channel_ai_enabled: bool = Form(False), channel_ai_hour: int = Form(8),
                           staff: Staff = Depends(admin_required)):
    await settings.set_many({"channel_ai_enabled": channel_ai_enabled, "channel_ai_hour": max(0, min(23, channel_ai_hour))})
    flash(request, "Saqlandi")
    return back("/channel#settings")


@router.post("/channel/import")
async def channel_import(request: Request, file: UploadFile = File(...), staff: Staff = Depends(admin_required)):
    ch = await tgchats.main_channel()
    if not ch:
        flash(request, "Avval asosiy kanalni ulang", "danger")
        return back("/channel")
    raw = await file.read()
    if len(raw) > IMPORT_LIMIT_MB * 1024 * 1024:
        flash(request, f"Fayl {IMPORT_LIMIT_MB} MB dan katta. Eksportda media fayllarni belgilamang — faqat JSON kerak.", "danger")
        return back("/channel#import")
    try:
        res = await channel.import_export(raw, ch.chat_id)
    except Exception as e:  # noqa: BLE001
        flash(request, f"Import xatosi: {e}", "danger")
        return back("/channel#import")
    await audit.log(staff.id, "channel", "channel_import", ch.chat_id, f"+{res['added']} post, {res['updated']} yangilandi")
    flash(request, f"✅ Import: {res['added']} ta yangi post, {res['updated']} ta yangilandi"
                   + (f", {res['skipped']} ta xizmat xabari o'tkazib yuborildi" if res["skipped"] else ""))
    return back("/channel")


@router.post("/channel/invites/add")
async def invite_add(request: Request, name: str = Form(...), staff: Staff = Depends(admin_required)):
    ch = await tgchats.main_channel()
    name = name.strip()
    if not ch or not name:
        flash(request, "Kanal ulanmagan yoki nom bo'sh", "danger")
        return back("/channel#invites")
    try:
        inv = await channel.create_invite(ch.chat_id, name, staff.id)
    except Exception as e:  # noqa: BLE001
        flash(request, f"Havola yaratib bo'lmadi: {e}. Botda «Taklif havolalari» huquqi borligini tekshiring.", "danger")
        return back("/channel#invites")
    flash(request, f"✅ Havola yaratildi: {inv.link}")
    return back("/channel#invites")


@router.post("/channel/invites/{inv_id}/revoke")
async def invite_revoke(inv_id: int, request: Request, staff: Staff = Depends(admin_required)):
    await channel.revoke_invite(inv_id)
    flash(request, "Havola bekor qilindi")
    return back("/channel#invites")


# ================================================================ o'quv guruhlari


@router.get("/groups")
async def groups_page(request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        rows = (await s.execute(select(TgChat).order_by(TgChat.title))).scalars().all()
    study = [c for c in rows if c.role == "study" and c.is_active and not c.removed_at]
    others = [c for c in rows if c.role != "study" and c.is_active and not c.removed_at]
    removed = [c for c in rows if not c.is_active or c.removed_at]
    changes = {c.chat_id: (await tgchats.change_since(c.chat_id, 7)) for c in study}
    hist = await tgchats.history([c.chat_id for c in study], 30)
    days = [(tgchats.today() - timedelta(days=i)) for i in range(29, -1, -1)]
    total = []
    for d in days:
        n, has = 0, False
        for c in study:
            vals = [r for r in hist.get(c.chat_id, []) if r.day <= d]
            if vals:
                has = True
                n += max(0, vals[-1].members - (c.admins or 0))
        total.append(n if has else None)  # hisob boshlanishidan oldingi kunlar grafikda chiqmaydi
    chart = {"labels": [d.strftime("%d.%m") for d in days], "total": total}
    return render(request, "growth/groups.html", staff, study=study, others=others, removed=removed, changes=changes,
                  roles=CHAT_ROLES, chart=chart, students_total=sum(c.students for c in study))


@router.post("/groups/register")
async def groups_register(request: Request, ref: str = Form(...), staff: Staff = Depends(admin_required)):
    ref = ref.strip()
    target: int | str = int(ref) if ref.lstrip("-").isdigit() else "@" + ref.lstrip("@").rsplit("/", 1)[-1]
    try:
        x = await tgchats.register(target)
        flash(request, f"✅ Qo'shildi: {x.title} ({CHAT_ROLES.get(x.role, x.role)})")
    except Exception as e:  # noqa: BLE001
        flash(request, f"Chatni topib bo'lmadi: {e}. Bot shu guruhga qo'shilganmi?", "danger")
    return back("/groups")


@router.post("/groups/refresh")
async def groups_refresh_all(request: Request, staff: Staff = Depends(admin_required)):
    n = await tgchats.snapshot_all()
    flash(request, f"🔄 {n} ta chat yangilandi")
    return back("/groups")


@router.post("/groups/{chat_id}/refresh")
async def group_refresh(chat_id: int, request: Request, staff: Staff = Depends(admin_required)):
    await tgchats.refresh(chat_id)
    flash(request, "Yangilandi")
    return back("/groups")


@router.post("/groups/{chat_id}/role")
async def group_role(chat_id: int, request: Request, role: str = Form(...), staff: Staff = Depends(admin_required)):
    if role not in CHAT_ROLES:
        return back("/groups")
    if role == "premium":
        from ...services import subscriptions

        await settings.set_value("group_chat_id", chat_id)
        async with session_scope() as s:
            for x in (await s.execute(select(TgChat).where(TgChat.role == "premium", TgChat.chat_id != chat_id))).scalars().all():
                x.role = "unassigned"
        _ = subscriptions
    await tgchats.set_role(chat_id, role)
    await audit.log(staff.id, "tg_chat", "tg_chat", chat_id, f"Vazifa: {CHAT_ROLES[role]}")
    flash(request, f"Saqlandi: {CHAT_ROLES[role]}")
    return back("/groups")


@router.post("/groups/{chat_id}/remove")
async def group_remove(chat_id: int, request: Request, staff: Staff = Depends(admin_required)):
    x = await tgchats.get(chat_id)
    if x and x.role == "premium":
        flash(request, "Premium guruhni bu yerdan o'chirib bo'lmaydi — avval Sozlamalarda boshqa guruhni tanlang", "danger")
        return back("/groups")
    ok = await tgchats.remove(chat_id)
    await audit.log(staff.id, "tg_chat", "tg_chat", chat_id, f"O'chirildi: {x.title if x else chat_id}")
    flash(request, "🗑 Guruh o'chirildi va bot guruhdan chiqdi" if ok else "Ro'yxatdan o'chirildi (botni guruhdan chiqarib bo'lmadi)",
          "success" if ok else "warning")
    return back("/groups")


# ================================================================ guruhlarga post


@router.get("/groups/posts")
async def posts_page(request: Request, staff: Staff = Depends(admin_required)):
    study = await tgchats.list_chats("study")
    async with session_scope() as s:
        posts = (await s.execute(select(GroupPost).where(GroupPost.dest == "groups").order_by(GroupPost.id.desc()).limit(50))).scalars().all()
    titles = {c.chat_id: c.title for c in await tgchats.list_chats(active_only=False)}
    default_time = (worktime.now_local() + timedelta(hours=1)).replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")
    return render(request, "growth/posts.html", staff, study=study, posts=posts, titles=titles, statuses=POST_STATUSES,
                  default_time=default_time)


def _back_for(dest: str) -> str:
    return "/channel#cposts" if dest == "channel" else "/groups/posts"


async def _create_post(request: Request, staff: Staff, dest: str, text: str, targets: list[int], mode: str,
                       scheduled_at: str, pin: bool, silent: bool, file: UploadFile | None, note: str | None = None):
    """Umumiy: o'quv guruhlariga yoki asosiy kanalga post (sinov / hozir / rejalashtirish)."""
    url = _back_for(dest)
    text = text.strip()
    kind, path, fname = "text", None, None
    if file and file.filename:
        data = await file.read()
        ctype = (file.content_type or "").lower()
        if ctype.startswith("image/"):
            kind, limit = "photo", PHOTO_LIMIT_MB
        elif ctype.startswith("video/"):
            kind, limit = "video", media.TELEGRAM_UPLOAD_LIMIT_MB
        else:
            flash(request, "Faqat rasm (jpg, png) yoki video (mp4) yuklash mumkin", "danger")
            return back(url)
        if len(data) > limit * 1024 * 1024:
            flash(request, f"Fayl juda katta ({len(data) // 1024 // 1024} MB). Ruxsat: {'rasm' if kind == 'photo' else 'video'} {limit} MB gacha.", "danger")
            return back(url)
        path = media.new_path(media.guess_ext(file.filename, file.content_type, ".mp4" if kind == "video" else ".jpg"), "posts")
        path.write_bytes(data)
        fname = file.filename
    err = group_posts.validate(kind, text)
    if err:
        flash(request, err, "danger")
        return back(url)
    if mode != "test" and not targets:
        flash(request, "Kamida bitta guruhni tanlang" if dest == "groups" else "Asosiy kanal ulanmagan", "danger")
        return back(url)
    when = utcnow()
    status = "scheduled"
    if mode == "schedule":
        try:
            when = worktime.local_to_utc_naive(datetime.fromisoformat(scheduled_at))
        except ValueError:
            flash(request, "Yuborish vaqtini to'g'ri kiriting", "danger")
            return back(url)
        if when <= utcnow():
            flash(request, "Rejalashtirilgan vaqt kelajakda bo'lishi kerak", "danger")
            return back(url)
    elif mode == "test":
        status, when = "draft", None
    async with session_scope() as s:
        post = GroupPost(kind=kind, dest=dest, note=(note or "")[:255] or None, text=text, file_path=str(path) if path else None,
                         file_name=fname, targets=targets, scheduled_at=when, pin=pin, silent=silent, status=status,
                         created_by_id=staff.id)
        s.add(post)
        await s.flush()
        pid = post.id
        where = "kanal" if dest == "channel" else f"{len(targets)} ta guruh"
        await audit.log(staff.id, "group_post", "group_post", pid, f"{kind}, {where}, {mode}", session=s)
    if mode == "test":
        err = await group_posts.send_test(pid, staff.tg_id) if staff.tg_id else "Telegram akkauntingiz biriktirilmagan"
        flash(request, f"Sinov xatosi: {err}" if err else "📲 Post Telegramingizga yuborildi. Hammasi to'g'ri bo'lsa — qoralamani tasdiqlang (hozir yoki belgilangan vaqtda).",
              "danger" if err else "success")
    elif mode == "schedule":
        flash(request, f"🕒 Tasdiqlandi va rejalashtirildi: {worktime.fmt(when)} da avtomatik joylanadi")
    else:
        p = await group_posts.send(pid)
        ok = sum(1 for d in p.deliveries if d.ok) if p else 0
        if dest == "channel":
            flash(request, "✅ Post kanalga joylandi" if ok else f"Kanalga joylab bo'lmadi: {p.deliveries[0].error if p and p.deliveries else ''}",
                  "success" if ok else "danger")
        else:
            flash(request, f"✅ Post {ok}/{len(targets)} ta guruhga yuborildi", "success" if p and p.status == "sent" else "warning")
    return back(url)


@router.post("/groups/posts/new")
async def post_new(request: Request, text: str = Form(""), targets: list[int] = Form([]), mode: str = Form("now"),
                   scheduled_at: str = Form(""), pin: bool = Form(False), silent: bool = Form(False),
                   file: UploadFile | None = File(None), staff: Staff = Depends(admin_required)):
    study = {c.chat_id for c in await tgchats.list_chats("study")}
    targets = [t for t in targets if t in study]
    return await _create_post(request, staff, "groups", text, targets, mode, scheduled_at, pin, silent, file)


@router.post("/channel/posts/new")
async def channel_post_new(request: Request, text: str = Form(""), mode: str = Form("schedule"), scheduled_at: str = Form(""),
                           pin: bool = Form(False), silent: bool = Form(False), note: str = Form(""),
                           file: UploadFile | None = File(None), staff: Staff = Depends(admin_required)):
    """Asosiy kanalga post: AI g'oyasidan yoki qo'lda; tasdiqlangach belgilangan vaqtda avtomatik joylanadi."""
    ch = await tgchats.main_channel()
    targets = [ch.chat_id] if ch and ch.is_active else []
    return await _create_post(request, staff, "channel", text, targets, mode, scheduled_at, pin, silent, file, note)


async def _post_dest(pid: int) -> str:
    async with session_scope() as s:
        p = await s.get(GroupPost, pid)
        return p.dest if p else "groups"


@router.post("/groups/posts/{pid}/send")
async def post_send(pid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        p = await s.get(GroupPost, pid)
        dest = p.dest if p else "groups"
        if not p or p.status != "draft" or not p.targets:
            flash(request, "Bu postni yuborib bo'lmaydi (guruhlar tanlanmagan?)", "danger")
            return back(_back_for(dest))
        p.status, p.scheduled_at = "scheduled", utcnow()
    p = await group_posts.send(pid)
    flash(request, f"Yuborildi: {p.status_label}")
    return back(_back_for(dest))


@router.post("/groups/posts/{pid}/schedule")
async def post_schedule(pid: int, request: Request, scheduled_at: str = Form(...), staff: Staff = Depends(admin_required)):
    """Qoralamani tasdiqlash: belgilangan vaqtda avtomatik yuboriladi."""
    try:
        when = worktime.local_to_utc_naive(datetime.fromisoformat(scheduled_at))
    except ValueError:
        flash(request, "Vaqtni to'g'ri kiriting", "danger")
        return back(_back_for(await _post_dest(pid)))
    async with session_scope() as s:
        p = await s.get(GroupPost, pid)
        dest = p.dest if p else "groups"
        if not p or p.status not in ("draft", "scheduled") or not p.targets:
            flash(request, "Bu postni rejalashtirib bo'lmaydi", "danger")
            return back(_back_for(dest))
        if when <= utcnow():
            flash(request, "Vaqt kelajakda bo'lishi kerak", "danger")
            return back(_back_for(dest))
        p.status, p.scheduled_at = "scheduled", when
    await audit.log(staff.id, "group_post", "group_post", pid, f"Tasdiqlandi: {scheduled_at}")
    flash(request, f"🕒 Tasdiqlandi: {worktime.fmt(when)} da avtomatik joylanadi")
    return back(_back_for(dest))


@router.post("/groups/posts/{pid}/cancel")
async def post_cancel(pid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        p = await s.get(GroupPost, pid)
        if p and p.status in ("scheduled", "draft"):
            p.status = "cancelled"
    flash(request, "Bekor qilindi")
    return back(_back_for(p.dest if p else "groups"))


@router.post("/groups/posts/{pid}/unsend")
async def post_unsend(pid: int, request: Request, staff: Staff = Depends(admin_required)):
    dest = await _post_dest(pid)
    ok, fail = await group_posts.delete_from_groups(pid)
    await audit.log(staff.id, "group_post", "group_post", pid, f"Guruhlardan o'chirildi: {ok}")
    flash(request, (f"🗑 {ok} ta guruhdan o'chirildi" if dest == "groups" else ("🗑 Post kanaldan o'chirildi" if ok else "Kanaldan o'chirilmadi"))
          + (f", {fail} tasida xato (Telegram 48 soatdan eski xabarni o'chirmasligi mumkin)" if fail else ""),
          "success" if not fail else "warning")
    return back(_back_for(dest))


@router.post("/groups/posts/{pid}/remove")
async def post_remove(pid: int, request: Request, staff: Staff = Depends(admin_required)):
    from pathlib import Path

    dest = await _post_dest(pid)
    async with session_scope() as s:
        p = await s.get(GroupPost, pid)
        if p and p.status in ("draft", "cancelled", "failed", "deleted", "sent", "partial"):
            if p.file_path:
                Path(p.file_path).unlink(missing_ok=True)
            await s.delete(p)
    flash(request, "Ro'yxatdan o'chirildi")
    return back(_back_for(dest))
