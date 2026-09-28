"""To'lovlar, obunachilar (yopiq guruh) va tizim holati."""
from __future__ import annotations

import math
from collections import Counter
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import String, func, or_, select

from ...db import session_scope, utcnow
from ...models import PAYMENT_STATES, Lead, Payment, Staff, Subscription, SubscriptionEvent
from ...services import audit, health, stats, subscriptions, worktime
from ..deps import admin_required, flash, parse_range, render

router = APIRouter()


# ================================================================ to'lovlar


async def revenue_series(start: date, end: date) -> dict:
    s0, s1 = stats.range_utc(start, end)
    async with session_scope() as s:
        paid = (await s.execute(select(Payment.paid_at, Payment.amount).where(Payment.paid_at >= s0, Payment.paid_at < s1,
                                                                             Payment.state == 2))).all()
        refunded = (await s.execute(select(Payment.cancelled_at, Payment.amount).where(
            Payment.cancelled_at >= s0, Payment.cancelled_at < s1, Payment.state == -2))).all()
    days = stats.day_range(start, end)
    inc, ref, cnt = Counter(), Counter(), Counter()
    for dt, amount in paid:
        d = worktime.to_local(dt).date()
        inc[d] += amount
        cnt[d] += 1
    for dt, amount in refunded:
        ref[worktime.to_local(dt).date()] += amount
    return {"labels": [d.strftime("%d.%m") for d in days], "dates": [d.isoformat() for d in days],
            "income": [inc.get(d, 0) for d in days], "refund": [ref.get(d, 0) for d in days], "count": [cnt.get(d, 0) for d in days]}


async def revenue_monthly(n: int = 12) -> dict:
    keys = stats.month_keys(n)
    y, m = map(int, keys[0].split("-"))
    s0, _ = stats.range_utc(date(y, m, 1), worktime.now_local().date())
    async with session_scope() as s:
        rows = (await s.execute(select(Payment.paid_at, Payment.amount).where(Payment.paid_at >= s0, Payment.state == 2))).all()
    c, n_ = Counter(), Counter()
    for dt, amount in rows:
        k = worktime.to_local(dt).strftime("%Y-%m")
        c[k] += amount
        n_[k] += 1
    return {"labels": keys, "income": [c.get(k, 0) for k in keys], "count": [n_.get(k, 0) for k in keys]}


async def revenue_kpis() -> dict:
    today = worktime.now_local().date()
    t0, t1 = stats.range_utc(today, today)
    m0, _ = stats.range_utc(today.replace(day=1), today)
    async with session_scope() as s:
        q = select(func.coalesce(func.sum(Payment.amount), 0), func.count(Payment.id)).where(Payment.state == 2)
        day_sum, day_cnt = (await s.execute(q.where(Payment.paid_at >= t0, Payment.paid_at < t1))).one()
        month_sum, month_cnt = (await s.execute(q.where(Payment.paid_at >= m0))).one()
        total_sum, total_cnt = (await s.execute(q)).one()
        active = (await s.execute(select(func.count(Subscription.id)).where(
            or_(Subscription.whitelisted.is_(True), Subscription.expires_at > utcnow())))).scalar_one()
        soon = (await s.execute(select(func.count(Subscription.id)).where(
            Subscription.whitelisted.is_(False), Subscription.expires_at > utcnow(),
            Subscription.expires_at < utcnow() + timedelta(days=3)))).scalar_one()
    return {"day_sum": day_sum, "day_cnt": day_cnt, "month_sum": month_sum, "month_cnt": month_cnt,
            "total_sum": total_sum, "total_cnt": total_cnt, "active_subs": active, "expiring": soon}


@router.get("/payments")
async def payments_page(request: Request, state: str = "", q: str = "", start: str = "", end: str = "", page: int = 1,
                        staff: Staff = Depends(admin_required)):
    s_, e_ = parse_range(start, end, 30)
    r0, r1 = stats.range_utc(s_, e_)
    async with session_scope() as s:
        query = select(Payment).where(Payment.created_at >= r0, Payment.created_at < r1)
        if state.lstrip("-").isdigit():
            query = query.where(Payment.state == int(state))
        if q:
            like = f"%{q}%"
            query = query.outerjoin(Lead, Lead.id == Payment.lead_id).where(
                or_(Lead.name.ilike(like), Lead.phone.ilike(like), Payment.payme_id.ilike(like),
                    func.cast(Payment.tg_id, String).ilike(like)))
        total = (await s.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        rows = (await s.execute(query.order_by(Payment.id.desc()).offset((page - 1) * 50).limit(50))).scalars().all()
    return render(request, "billing/payments.html", staff, rows=rows, total=total, page=page, pages=max(1, math.ceil(total / 50)),
                  states=PAYMENT_STATES, k=await revenue_kpis(), daily=await revenue_series(s_, e_), monthly=await revenue_monthly(),
                  f={"state": state, "q": q, "start": s_.isoformat(), "end": e_.isoformat()})


# ================================================================ obunachilar


@router.get("/subscriptions")
async def subs_page(request: Request, flt: str = "active", q: str = "", staff: Staff = Depends(admin_required)):
    now = utcnow()
    async with session_scope() as s:
        query = select(Subscription)
        if flt == "active":
            query = query.where(or_(Subscription.whitelisted.is_(True), Subscription.expires_at > now))
        elif flt == "expiring":
            query = query.where(Subscription.whitelisted.is_(False), Subscription.expires_at > now,
                                Subscription.expires_at < now + timedelta(days=7))
        elif flt == "expired":
            query = query.where(Subscription.whitelisted.is_(False), Subscription.expires_at <= now)
        if q:
            like = f"%{q}%"
            query = query.where(or_(Subscription.name.ilike(like), Subscription.note.ilike(like),
                                    func.cast(Subscription.tg_id, String).ilike(like)))
        rows = (await s.execute(query.order_by(Subscription.expires_at))).scalars().all()
        events = (await s.execute(select(SubscriptionEvent).order_by(SubscriptionEvent.id.desc()).limit(40))).scalars().all()
        sub_names = {x.id: (x.name or str(x.tg_id)) for x in (await s.execute(select(Subscription))).scalars().all()}
    return render(request, "billing/subscriptions.html", staff, rows=rows, events=events, sub_names=sub_names,
                  labels=subscriptions.EVENT_LABELS, flt=flt, q=q, k=await revenue_kpis(),
                  group_id=await subscriptions.group_id(), link=request.query_params.get("link"))


def _tg(raw: str) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


@router.post("/subscriptions/add")
async def subs_add(request: Request, tg_id: str = Form(...), days: int = Form(30), name: str = Form(""), note: str = Form(""),
                   whitelisted: bool = Form(False), send_link: bool = Form(False), staff: Staff = Depends(admin_required)):
    uid = _tg(tg_id)
    if not uid:
        flash(request, "Telegram ID noto'g'ri", "danger")
        return RedirectResponse("/subscriptions", 303)
    if days <= 0 and not whitelisted:
        flash(request, "Kunlar soni 0 dan katta bo'lishi kerak", "danger")
        return RedirectResponse("/subscriptions", 303)
    sub = await subscriptions.extend(uid, max(days, 0), kind="manual", staff_id=staff.id, note=note.strip() or None,
                                     name=name.strip() or None, whitelisted=whitelisted or None)
    await audit.log(staff.id, "subscription_add", "subscription", sub.id, f"{uid}: +{days} kun" + (" (muddatsiz)" if whitelisted else ""))
    st = await subscriptions.member_status(uid)
    if st in ("member", "administrator", "creator", "restricted"):
        async with session_scope() as s:
            obj = await s.get(Subscription, sub.id)
            obj.in_group = True
        flash(request, f"✅ Obuna berildi: {subscriptions.fmt_date(sub.expires_at) if not sub.whitelisted else 'muddatsiz'} gacha. Foydalanuvchi allaqachon guruhda.")
        return RedirectResponse("/subscriptions", 303)
    if send_link:
        ok, link, err = await subscriptions.send_access(uid, "access_granted", staff_id=staff.id)
        if ok:
            flash(request, "✅ Obuna berildi va guruh havolasi foydalanuvchiga bot orqali yuborildi.")
        elif link:
            flash(request, f"✅ Obuna berildi. ⚠️ {err}", "warning")
            return RedirectResponse(f"/subscriptions?link={link}", 303)
        else:
            flash(request, f"✅ Obuna berildi. ⚠️ {err}", "warning")
    else:
        flash(request, "✅ Obuna berildi.")
    return RedirectResponse("/subscriptions", 303)


@router.post("/subscriptions/{sid}/extend")
async def subs_extend(sid: int, request: Request, days: int = Form(...), staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        sub = await s.get(Subscription, sid)
    if not sub:
        return RedirectResponse("/subscriptions", 303)
    if days > 0:
        sub = await subscriptions.extend(sub.tg_id, days, kind="manual", staff_id=staff.id, note=f"+{days} kun")
    elif days < 0:
        local = worktime.to_local(sub.expires_at) + timedelta(days=days)
        sub = await subscriptions.set_expiry(sub.tg_id, local.replace(tzinfo=None), staff.id)
    await audit.log(staff.id, "subscription_edit", "subscription", sid, f"{days:+d} kun")
    flash(request, f"Muddat o'zgartirildi: {subscriptions.fmt_date(sub.expires_at) if sub else '—'}")
    return RedirectResponse(request.headers.get("referer") or "/subscriptions", 303)


@router.post("/subscriptions/{sid}/set")
async def subs_set(sid: int, request: Request, expires: str = Form(""), whitelisted: bool = Form(False), note: str = Form(""),
                   staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        sub = await s.get(Subscription, sid)
    if not sub:
        return RedirectResponse("/subscriptions", 303)
    try:
        d = date.fromisoformat(expires) if expires else worktime.to_local(sub.expires_at).date()
    except ValueError:
        flash(request, "Sana noto'g'ri", "danger")
        return RedirectResponse("/subscriptions", 303)
    local = datetime.combine(d, datetime.max.time().replace(microsecond=0))
    await subscriptions.set_expiry(sub.tg_id, local, staff.id, whitelisted=whitelisted, note=note)
    await audit.log(staff.id, "subscription_edit", "subscription", sid, f"{d.isoformat()}{' muddatsiz' if whitelisted else ''}")
    flash(request, "Obuna yangilandi")
    return RedirectResponse(request.headers.get("referer") or "/subscriptions", 303)


@router.post("/subscriptions/{sid}/revoke")
async def subs_revoke(sid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        sub = await s.get(Subscription, sid)
    if sub:
        await subscriptions.revoke(sub.tg_id, staff.id, "Admin bekor qildi")
        await audit.log(staff.id, "subscription_revoke", "subscription", sid, str(sub.tg_id))
    flash(request, "Obuna bekor qilindi va foydalanuvchi guruhdan chiqarildi")
    return RedirectResponse(request.headers.get("referer") or "/subscriptions", 303)


@router.post("/subscriptions/{sid}/link")
async def subs_link(sid: int, request: Request, staff: Staff = Depends(admin_required)):
    async with session_scope() as s:
        sub = await s.get(Subscription, sid)
    if not sub:
        return RedirectResponse("/subscriptions", 303)
    ok, link, err = await subscriptions.send_access(sub.tg_id, "access_granted", staff_id=staff.id)
    if ok:
        flash(request, "Guruh havolasi bot orqali yuborildi")
        return RedirectResponse("/subscriptions", 303)
    flash(request, err or "Xatolik", "warning")
    return RedirectResponse(f"/subscriptions?link={link}" if link else "/subscriptions", 303)


@router.post("/subscriptions/sync")
async def subs_sync(request: Request, staff: Staff = Depends(admin_required)):
    try:
        r = await subscriptions.sync_group()
        flash(request, f"Sinxronlandi: {r['total']} obunachidan {r['in_group']} tasi guruhda")
    except Exception as e:  # noqa: BLE001
        flash(request, f"Xatolik: {e}", "danger")
    return RedirectResponse("/subscriptions", 303)


@router.post("/subscriptions/check")
async def subs_check(request: Request, staff: Staff = Depends(admin_required)):
    r = await subscriptions.daily_check()
    flash(request, f"Tekshirildi: {r['reminded']} ta eslatma yuborildi, {r['removed']} ta muddati tugagan chiqarildi")
    return RedirectResponse("/subscriptions", 303)


# ================================================================ tizim holati


@router.get("/system")
async def system_page(request: Request, staff: Staff = Depends(admin_required)):
    items = await health.all_checks()
    counts = Counter(i["status"] for i in items)
    return render(request, "billing/system.html", staff, items=items, counts=counts, errors=list(health.errors)[:50],
                  uptime=health.ago(health.started_at).replace(" oldin", ""), fmt_ts=lambda ts: datetime.fromtimestamp(ts, worktime.TZ).strftime("%d.%m %H:%M:%S"))


@router.post("/system/fix/{action}")
async def system_fix(action: str, request: Request, staff: Staff = Depends(admin_required)):
    try:
        msg = await health.run_fix(action)
        await audit.log(staff.id, "system_fix", "system", None, f"{action}: {msg}"[:500])
        flash(request, f"✅ {msg}")
    except Exception as e:  # noqa: BLE001
        flash(request, f"❌ {e}", "danger")
    return RedirectResponse("/system", 303)


@router.get("/api/system/status")
async def system_status(staff: Staff = Depends(admin_required)):
    items = await health.all_checks()
    return JSONResponse({"items": items})


@router.get("/api/system/brief")
async def system_brief(staff: Staff = Depends(admin_required)):
    fails = [k for k, v in health._last_status.items() if v == "fail"]
    return {"fails": len(fails)}
