"""Asosiy Telegram kanalni rivojlantirish: postlar va reaksiyalar tahlili, obunachilar o'sishi,
taklif havolalari, Telegram Desktop eksportini import qilish va OpenAI orqali kunlik kontent g'oyalari.

Telegram Bot API cheklovlari (va ularni qanday chetlab o'tamiz):
- Bot kanalga admin bo'lgandan KEYINGI postlarni ko'radi → eski postlar Telegram Desktop JSON eksporti orqali import qilinadi.
- Ko'rishlar soni (views) Bot API'da yo'q → faollik o'lchovi: reaksiyalar (message_reaction_count) va
  post vaqtidagi obunachilar soniga nisbati; eksportda views bo'lsa — u ham olinadi.
- Obunachilar: kunlik son + qo'shilgan/chiqib ketganlar (chat_member) + nomlangan taklif havolalari bo'yicha.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from ..db import session_scope, utcnow
from ..models import ChannelInsight, ChannelInvite, ChannelPost, ChatStat, Lead, Source, TgChat
from . import settings, tgchats, worktime

log = logging.getLogger(__name__)

KIND_LABELS = {
    "text": "📝 Matn", "photo": "🖼 Rasm", "video": "🎬 Video", "album": "🗂 Albom", "animation": "🎞 GIF",
    "audio": "🎵 Audio", "voice": "🎙 Ovozli", "video_note": "⭕️ Dumaloq video", "document": "📎 Fayl",
    "poll": "📊 So'rovnoma", "sticker": "🙂 Stiker", "other": "• Boshqa",
}
WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
FUNNEL_PREFIXES = ("kanal", "channel", "telegram", "atko_teams")


# ------------------------------------------------------------------ jonli postlar


def _kind_of(msg) -> tuple[str, int | None]:
    if msg.video:
        return "video", msg.video.duration
    if msg.photo:
        return "photo", None
    if msg.animation:
        return "animation", msg.animation.duration
    if msg.video_note:
        return "video_note", msg.video_note.duration
    if msg.voice:
        return "voice", msg.voice.duration
    if msg.audio:
        return "audio", msg.audio.duration
    if msg.document:
        return "document", None
    if msg.poll:
        return "poll", None
    if msg.sticker:
        return "sticker", None
    if msg.text:
        return "text", None
    return "other", None


async def is_main_channel(chat_id: int) -> bool:
    x = await tgchats.get(chat_id)
    return bool(x and x.role == "channel")


async def on_post(msg, edited: bool = False) -> None:
    """channel_post / edited_channel_post"""
    if not await is_main_channel(msg.chat.id):
        return
    kind, duration = _kind_of(msg)
    text = (msg.text or msg.caption or "")[:8000]
    ch = await tgchats.get(msg.chat.id)
    async with session_scope() as s:
        # albom: bitta media_group — bitta post sifatida hisoblaymiz
        if msg.media_group_id and not edited:
            first = (await s.execute(select(ChannelPost).where(ChannelPost.chat_id == msg.chat.id,
                                                               ChannelPost.media_group_id == msg.media_group_id))).scalars().first()
            if first:
                first.kind = "album"
                if text and not first.text:
                    first.text = text
                return
        p = (await s.execute(select(ChannelPost).where(ChannelPost.chat_id == msg.chat.id,
                                                       ChannelPost.message_id == msg.message_id))).scalars().first()
        if p is None:
            p = ChannelPost(chat_id=msg.chat.id, message_id=msg.message_id,
                            posted_at=msg.date.astimezone(timezone.utc).replace(tzinfo=None),
                            subscribers_at_post=ch.members if ch else None, source="live")
            s.add(p)
        p.kind, p.duration, p.media_group_id = kind, duration, msg.media_group_id
        if text or not edited:
            p.text = text
        p.edited = p.edited or edited


async def on_reactions(upd) -> None:
    """message_reaction_count — kanal postidagi anonim reaksiyalar soni."""
    if not await is_main_channel(upd.chat.id):
        return
    detail: dict[str, int] = {}
    for r in upd.reactions or []:
        t = r.type
        key = getattr(t, "emoji", None) or ("custom" if getattr(t, "custom_emoji_id", None) else "paid")
        detail[key] = detail.get(key, 0) + int(r.total_count or 0)
    async with session_scope() as s:
        p = (await s.execute(select(ChannelPost).where(ChannelPost.chat_id == upd.chat.id,
                                                       ChannelPost.message_id == upd.message_id))).scalars().first()
        if p is None:
            p = ChannelPost(chat_id=upd.chat.id, message_id=upd.message_id, posted_at=utcnow(), kind="other", source="live")
            s.add(p)
        p.reactions = sum(detail.values())
        p.reactions_detail = detail


# ------------------------------------------------------------------ Telegram Desktop eksporti


def _export_text(v: Any) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(x if isinstance(x, str) else str(x.get("text", "")) for x in v)
    return ""


def _export_kind(m: dict) -> str:
    mt = m.get("media_type")
    if m.get("photo"):
        return "photo"
    return {"video_file": "video", "animation": "animation", "voice_message": "voice", "video_message": "video_note",
            "audio_file": "audio", "sticker": "sticker"}.get(mt, "poll" if m.get("poll") else ("document" if m.get("file") else "text"))


async def import_export(raw: bytes, chat_id: int) -> dict[str, int]:
    """Telegram Desktop → «Export chat history» → JSON (result.json). Mavjud postlar yangilanadi."""
    data = json.loads(raw.decode("utf-8-sig"))
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list):
        raise ValueError("Bu Telegram Desktop eksporti emas (result.json ichida «messages» topilmadi)")
    added = updated = skipped = 0
    async with session_scope() as s:
        existing = {p.message_id: p for p in (await s.execute(select(ChannelPost).where(ChannelPost.chat_id == chat_id))).scalars().all()}
        for m in messages:
            if m.get("type") != "message" or not isinstance(m.get("id"), int):
                skipped += 1
                continue
            ts = m.get("date_unixtime")
            try:
                posted = datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None) if ts else \
                    worktime.local_to_utc_naive(datetime.fromisoformat(m["date"]))
            except Exception:  # noqa: BLE001
                skipped += 1
                continue
            reactions: dict[str, int] = {}
            for r in m.get("reactions") or []:
                key = r.get("emoji") or r.get("type") or "?"
                reactions[key] = reactions.get(key, 0) + int(r.get("count") or 0)
            text = _export_text(m.get("text"))[:8000]
            p = existing.get(m["id"])
            if p is None:
                p = ChannelPost(chat_id=chat_id, message_id=m["id"], posted_at=posted, source="import")
                s.add(p)
                existing[m["id"]] = p
                added += 1
            else:
                updated += 1
            p.kind = _export_kind(m)
            p.duration = m.get("duration_seconds")
            if text:
                p.text = text
            if reactions:
                p.reactions, p.reactions_detail = sum(reactions.values()), reactions
            if isinstance(m.get("views"), int):
                p.views = m["views"]
            p.edited = bool(m.get("edited"))
    return {"added": added, "updated": updated, "skipped": skipped}


# ------------------------------------------------------------------ taklif havolalari


async def create_invite(chat_id: int, name: str, staff_id: int | None) -> ChannelInvite:
    from ..bot.instance import get_bot

    link = await get_bot().create_chat_invite_link(chat_id, name=name[:32])
    async with session_scope() as s:
        inv = ChannelInvite(chat_id=chat_id, name=name[:32], link=link.invite_link, created_by_id=staff_id)
        s.add(inv)
        await s.flush()
        await s.refresh(inv)
    return inv


async def revoke_invite(inv_id: int) -> None:
    from ..bot.instance import get_bot

    async with session_scope() as s:
        inv = await s.get(ChannelInvite, inv_id)
        if not inv:
            return
        try:
            await get_bot().revoke_chat_invite_link(inv.chat_id, inv.link)
        except Exception as e:  # noqa: BLE001
            log.warning("Havolani bekor qilib bo'lmadi: %s", e)
        inv.is_active = False


# ------------------------------------------------------------------ statistika


def _rate(p: ChannelPost) -> float | None:
    if p.subscribers_at_post:
        return round(p.reactions * 100 / p.subscribers_at_post, 2)
    return None


async def stats(chat_id: int, days: int = 30) -> dict[str, Any]:
    now = utcnow()
    since = now - timedelta(days=days)
    async with session_scope() as s:
        posts = list((await s.execute(select(ChannelPost).where(ChannelPost.chat_id == chat_id, ChannelPost.posted_at >= since)
                                      .order_by(ChannelPost.posted_at.desc()))).scalars().all())
        all_posts = (await s.execute(select(func.count(ChannelPost.id)).where(ChannelPost.chat_id == chat_id))).scalar_one()
        invites = list((await s.execute(select(ChannelInvite).where(ChannelInvite.chat_id == chat_id)
                                        .order_by(ChannelInvite.is_active.desc(), ChannelInvite.joins.desc()))).scalars().all())
        sources = [x for x in (await s.execute(select(Source))).scalars().all() if x.code.lower().startswith(FUNNEL_PREFIXES)]
        counts = dict((await s.execute(select(Lead.source_id, func.count(Lead.id)).where(
            Lead.source_id.in_([x.id for x in sources] or [0]), Lead.created_at >= since).group_by(Lead.source_id))).all())
        acc = dict((await s.execute(select(Lead.source_id, func.count(Lead.id)).where(
            Lead.source_id.in_([x.id for x in sources] or [0]), Lead.created_at >= since, Lead.status == "accepted")
            .group_by(Lead.source_id))).all())
    hist = (await tgchats.history([chat_id], days)).get(chat_id, [])
    funnel = [{"code": x.code, "name": x.name, "leads": int(counts.get(x.id, 0)), "accepted": int(acc.get(x.id, 0))} for x in sources]

    by_kind: dict[str, list[int]] = defaultdict(list)
    by_hour: dict[int, list[int]] = defaultdict(list)
    by_wd: dict[int, list[int]] = defaultdict(list)
    for p in posts:
        local = worktime.to_local(p.posted_at)
        by_kind[p.kind].append(p.reactions)
        by_hour[local.hour].append(p.reactions)
        by_wd[local.weekday()].append(p.reactions)

    def agg(d: dict) -> list[dict]:
        return [{"key": k, "posts": len(v), "avg": round(sum(v) / len(v), 1) if v else 0} for k, v in d.items()]

    kinds = sorted(agg(by_kind), key=lambda x: -x["avg"])
    hours = sorted(agg(by_hour), key=lambda x: x["key"])
    wds = sorted(agg(by_wd), key=lambda x: x["key"])
    top = sorted(posts, key=lambda p: -p.reactions)[:5]
    joined = sum(r.joined for r in hist)
    left = sum(r.left for r in hist)
    growth = (hist[-1].members - hist[0].members) if len(hist) >= 2 else 0
    return {
        "posts": posts, "posts_total": all_posts, "hist": hist, "kinds": kinds, "hours": hours, "weekdays": wds, "top": top,
        "joined": joined, "left": left, "growth": growth, "invites": invites, "funnel": funnel,
        "avg_reactions": round(sum(p.reactions for p in posts) / len(posts), 1) if posts else 0,
        "posts_per_week": round(len(posts) / max(1, days / 7), 1),
    }


# ------------------------------------------------------------------ AI g'oyalar

AI_SYSTEM = """Sen ATKO koreys tili o'quv markazining Telegram kanali uchun SMM strateg va kontent-prodyuserisan.
Markaz: koreys tili, TOPIK va EPS-TOPIK (Koreyaga ishga borish imtihoni) bo'yicha tayyorlaydi.
Mahsulotlar: 💎 Premium yopiq Telegram guruh (video darslar, obuna), 🎥 Zoom orqali ustoz bilan guruh darslari, 👤 Zoom orqali individual darslar (har dars 120 daqiqa). Aniq narxlar kontekstda beriladi.
Auditoriya: O'zbekistondagi 17–35 yoshli yoshlar, ko'pchiligi Koreyaga ishlash yoki o'qish uchun.
Kanal maqsadi: obunachilarni ko'paytirish, faollikni oshirish va obunachilarni botga (@ kanal → bot) va kurslarga olib kelish.

Senga kanal statistikasi beriladi. Telegram Bot API ko'rishlar sonini bermaydi — faollik reaksiyalar va obunachilar o'sishi orqali baholanadi.
Faqat berilgan raqamlarga tayan, raqam o'ylab topma. Ma'lumot kam bo'lsa — buni ochiq ayt va umumiy eng yaxshi amaliyotga asoslan.
Javob faqat o'zbek tilida (lotin), JSON formatida:
{
 "summary": "2-3 gapli umumiy xulosa",
 "health_score": 0-100,
 "insights": ["statistikadan kelib chiqqan aniq kuzatishlar (3-6 ta)"],
 "actions_today": ["bugun qilinadigan 2-4 aniq ish"],
 "post_ideas": [{"title": "...", "format": "matn/rasm/albom/so'rovnoma/…", "goal": "faollik/obunachi/sotuv/…",
                 "best_time": "masalan Seshanba 19:00", "draft": "kanalga to'g'ridan-to'g'ri joylash mumkin bo'lgan tayyor post matni (emoji bilan, 400-900 belgi, oxirida chaqiriq; oddiy matn, HTML/markdown belgilarsiz)",
                 "hashtags": ["#..."]}],
 "video_ideas": [{"title": "...", "format": "Reels/qisqa video/dumaloq video/…", "duration": "30-60 s",
                  "hook": "birinchi 3 soniyadagi gap", "script": "qisqa ssenariy qadamlari", "cta": "yakuniy chaqiriq"}],
 "best_times": ["kun va soat, sababi bilan"],
 "weekly_plan": [{"day": "Dushanba", "content": "..."}],
 "warnings": ["e'tibor berish kerak bo'lgan salbiy tendensiyalar (bo'lmasa bo'sh)"]
}
post_ideas — 5 ta, video_ideas — 3 ta, weekly_plan — 7 kun."""


def _post_line(p: ChannelPost) -> str:
    local = worktime.to_local(p.posted_at)
    text = " ".join((p.text or "").split())[:220]
    rate = _rate(p)
    extra = f", faollik {rate}%" if rate is not None else ""
    views = f", ko'rish {p.views}" if p.views else ""
    return (f"- {local:%d.%m %a %H:%M} | {KIND_LABELS.get(p.kind, p.kind)} | reaksiya {p.reactions}{extra}{views}"
            f"{' | ' + str(p.duration) + 's' if p.duration else ''} | {text or '(matnsiz)'}")


async def build_context(chat_id: int) -> str:
    ch = await tgchats.get(chat_id)
    st30 = await stats(chat_id, 30)
    st90 = await stats(chat_id, 90)
    from . import tariffs as tariff_svc

    products = []
    for o in await tariff_svc.all_options():
        products.append(f"{o.tariff.name_uz}: {tariff_svc.option_title(o)} ({tariff_svc.option_details(o)}) — {tariff_svc.fmt_money(o.price)} so'm")
    lines = [f"Kanal: {ch.title if ch else chat_id} (@{ch.username if ch and ch.username else '—'}), obunachilar: {ch.members if ch else '?'}",
             f"Bugun: {worktime.now_local():%d.%m.%Y, %A}",
             "Kurs paketlari: " + ("; ".join(products) or "—"),
             f"30 kun: +{st30['joined']} qo'shildi, -{st30['left']} chiqdi, sof o'sish {st30['growth']:+d}; "
             f"postlar: {len(st30['posts'])} (haftasiga ~{st30['posts_per_week']}), o'rtacha reaksiya {st30['avg_reactions']}",
             f"90 kun: postlar {len(st90['posts'])}, o'rtacha reaksiya {st90['avg_reactions']}; bazadagi jami postlar: {st90['posts_total']}",
             "Post turlari bo'yicha o'rtacha reaksiya (90 kun): " + ", ".join(
                 f"{KIND_LABELS.get(k['key'], k['key'])} — {k['avg']} ({k['posts']} ta)" for k in st90["kinds"]) or "—",
             "Hafta kunlari bo'yicha: " + ", ".join(f"{WEEKDAYS[k['key']]} — {k['avg']} ({k['posts']})" for k in st90["weekdays"]) or "—",
             "Soatlar bo'yicha: " + ", ".join(f"{k['key']}:00 — {k['avg']} ({k['posts']})" for k in st90["hours"]) or "—"]
    if st30["hist"]:
        lines.append("Kunlik obunachilar (oxirgi 14 kun): " + ", ".join(f"{r.day:%d.%m}: {r.members} (+{r.joined}/-{r.left})"
                                                                      for r in st30["hist"][-14:]))
    if st30["invites"]:
        lines.append("Taklif havolalari (qaysi manbadan qancha obunachi): " + ", ".join(f"{i.name}: {i.joins}" for i in st30["invites"]))
    if st30["funnel"]:
        lines.append("Kanaldan botga kelgan leadlar (30 kun): " + ", ".join(f"{f['name']}: {f['leads']} lead, {f['accepted']} kursga yozildi"
                                                                         for f in st30["funnel"]))
    lines.append("\nEng faol postlar (90 kun):")
    lines += [_post_line(p) for p in st90["top"]] or ["—"]
    lines.append("\nOxirgi postlar:")
    lines += [_post_line(p) for p in st90["posts"][:25]] or ["— hali post yo'q"]
    return "\n".join(lines)


async def generate_ideas(trigger: str = "auto", staff_id: int | None = None) -> ChannelInsight | None:
    from . import ai

    ch = await tgchats.main_channel()
    if not ch:
        return None
    day = tgchats.today()
    data, error = None, None
    model = await settings.get("ai_model")
    try:
        ctx = await build_context(ch.chat_id)
        prev = await latest(ch.chat_id)
        prev_titles = ""
        if prev and prev.data:
            prev_titles = "\n\nOldingi kun berilgan g'oyalar (takrorlama): " + "; ".join(
                x.get("title", "") for x in (prev.data.get("post_ideas") or []) + (prev.data.get("video_ideas") or []))
        msg = await ai.complete([{"role": "system", "content": AI_SYSTEM},
                                 {"role": "user", "content": ctx + prev_titles}], max_tokens=6000, json_mode=True)
        data = json.loads(ai._strip_json(msg.content or "{}"))
    except ai.AIUnavailable:
        error = "OpenAI mavjud emas (kalit, limit yoki AI o'chirilgan)"
    except Exception as e:  # noqa: BLE001
        log.exception("Kanal g'oyalarini olishda xato")
        error = str(e)[:500]
    async with session_scope() as s:
        ins = ChannelInsight(chat_id=ch.chat_id, day=day, trigger=trigger, data=data, error=error, model=model,
                             created_by_id=staff_id)
        s.add(ins)
        await s.flush()
        await s.refresh(ins)
    if trigger == "auto":
        await settings.set_value("channel_ai_last_day", day.isoformat())
    return ins


async def latest(chat_id: int) -> ChannelInsight | None:
    async with session_scope() as s:
        return (await s.execute(select(ChannelInsight).where(ChannelInsight.chat_id == chat_id, ChannelInsight.data.is_not(None))
                                .order_by(ChannelInsight.id.desc()))).scalars().first()


async def daily_job() -> None:
    """Fon vazifasi: har kuni belgilangan soatda bitta tahlil (natija faqat panelda ko'rinadi)."""
    if not await settings.get("channel_ai_enabled"):
        return
    now = worktime.now_local()
    if now.hour < int(await settings.get("channel_ai_hour") or 8):
        return
    if str(await settings.get("channel_ai_last_day") or "") == now.date().isoformat():
        return
    if not await tgchats.main_channel():
        return
    await generate_ideas("auto")
