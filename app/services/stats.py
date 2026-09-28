"""Statistika hisob-kitoblari (Toshkent vaqti bo'yicha kunlik/oylik)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from ..db import session_scope
from ..models import LEAD_STATUSES, GOALS, AuditLog, Chat, Lead, Message, Source, Staff
from . import worktime


def _local_date(dt: datetime | None) -> date | None:
    d = worktime.to_local(dt)
    return d.date() if d else None


def day_range(start: date, end: date) -> list[date]:
    out = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def month_keys(n: int = 12) -> list[str]:
    today = worktime.now_local().date().replace(day=1)
    keys = []
    y, m = today.year, today.month
    for _ in range(n):
        keys.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(keys))


def range_utc(start: date, end: date) -> tuple[datetime, datetime]:
    s = worktime.local_to_utc_naive(datetime.combine(start, datetime.min.time()))
    e = worktime.local_to_utc_naive(datetime.combine(end + timedelta(days=1), datetime.min.time()))
    return s, e


async def dashboard() -> dict:
    today = worktime.now_local().date()
    month_start = today.replace(day=1)
    t0, t1 = range_utc(today, today)
    m0, _ = range_utc(month_start, today)
    async with session_scope() as s:
        total = (await s.execute(select(func.count(Lead.id)))).scalar_one()
        today_n = (await s.execute(select(func.count(Lead.id)).where(Lead.created_at >= t0, Lead.created_at < t1))).scalar_one()
        month_n = (await s.execute(select(func.count(Lead.id)).where(Lead.created_at >= m0))).scalar_one()
        with_phone = (await s.execute(select(func.count(Lead.id)).where(Lead.phone.is_not(None)))).scalar_one()
        accepted_total = (await s.execute(select(func.count(Lead.id)).where(Lead.status == "accepted"))).scalar_one()
        accepted_month = (await s.execute(select(func.count(Lead.id)).where(Lead.status == "accepted", Lead.accepted_at >= m0))).scalar_one()
        waiting = (await s.execute(select(func.count(Chat.id)).where(Chat.status == "waiting"))).scalar_one()
        active = (await s.execute(select(func.count(Chat.id)).where(Chat.status == "active"))).scalar_one()
        chats_today = (await s.execute(select(func.count(Chat.id)).where(Chat.requested_at >= t0, Chat.requested_at < t1))).scalar_one()
        avg_rating = (await s.execute(select(func.avg(Chat.rating)).where(Chat.rating.is_not(None)))).scalar_one()
        status_rows = (await s.execute(select(Lead.status, func.count(Lead.id)).group_by(Lead.status))).all()
    return {
        "total": total, "today": today_n, "month": month_n, "with_phone": with_phone,
        "accepted_total": accepted_total, "accepted_month": accepted_month,
        "conversion": round(accepted_total / total * 100, 1) if total else 0,
        "waiting": waiting, "active": active, "chats_today": chats_today,
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "by_status": {LEAD_STATUSES.get(k, k): v for k, v in status_rows},
    }


async def leads_series(start: date, end: date) -> dict:
    s0, s1 = range_utc(start, end)
    async with session_scope() as s:
        rows = (await s.execute(select(Lead.created_at, Lead.status, Lead.accepted_at, Lead.phone)
                                .where(Lead.created_at >= s0, Lead.created_at < s1))).all()
        acc = (await s.execute(select(Lead.accepted_at).where(Lead.accepted_at >= s0, Lead.accepted_at < s1))).scalars().all()
    days = day_range(start, end)
    new = Counter(_local_date(r[0]) for r in rows)
    phone = Counter(_local_date(r[0]) for r in rows if r[3])
    accepted = Counter(_local_date(a) for a in acc)
    return {
        "labels": [d.strftime("%d.%m") for d in days],
        "dates": [d.isoformat() for d in days],
        "new": [new.get(d, 0) for d in days],
        "with_phone": [phone.get(d, 0) for d in days],
        "accepted": [accepted.get(d, 0) for d in days],
    }


async def leads_monthly(n: int = 12) -> dict:
    keys = month_keys(n)
    y, m = map(int, keys[0].split("-"))
    s0, _ = range_utc(date(y, m, 1), worktime.now_local().date())
    async with session_scope() as s:
        created = (await s.execute(select(Lead.created_at).where(Lead.created_at >= s0))).scalars().all()
        acc = (await s.execute(select(Lead.accepted_at).where(Lead.accepted_at >= s0))).scalars().all()
    c_new = Counter(worktime.to_local(d).strftime("%Y-%m") for d in created)
    c_acc = Counter(worktime.to_local(d).strftime("%Y-%m") for d in acc if d)
    return {"labels": keys, "new": [c_new.get(k, 0) for k in keys], "accepted": [c_acc.get(k, 0) for k in keys]}


async def by_source(start: date, end: date) -> list[dict]:
    s0, s1 = range_utc(start, end)
    async with session_scope() as s:
        rows = (await s.execute(select(Lead.source_id, Lead.status, Lead.phone).where(Lead.created_at >= s0, Lead.created_at < s1))).all()
        sources = {x.id: x for x in (await s.execute(select(Source))).scalars().all()}
    agg: dict = defaultdict(lambda: {"leads": 0, "phone": 0, "accepted": 0})
    for sid, status, phone in rows:
        a = agg[sid]
        a["leads"] += 1
        a["phone"] += 1 if phone else 0
        a["accepted"] += 1 if status == "accepted" else 0
    out = []
    for sid, a in agg.items():
        src = sources.get(sid)
        out.append({"name": src.name if src else "To'g'ridan-to'g'ri (manbasiz)", "code": src.code if src else "—", **a,
                    "conv": round(a["accepted"] / a["leads"] * 100, 1) if a["leads"] else 0})
    out.sort(key=lambda x: x["leads"], reverse=True)
    return out


async def by_goal() -> dict:
    async with session_scope() as s:
        rows = (await s.execute(select(Lead.goal, func.count(Lead.id)).group_by(Lead.goal))).all()
    return {(GOALS.get(k, {}).get("uz") if k else "Noma'lum"): v for k, v in rows}


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


async def operator_stats(start: date, end: date, staff_id: int | None = None) -> list[dict]:
    s0, s1 = range_utc(start, end)
    async with session_scope() as s:
        q = select(Staff).order_by(Staff.is_active.desc(), Staff.full_name)
        if staff_id:
            q = q.where(Staff.id == staff_id)
        staff = (await s.execute(q)).scalars().all()
        chats = (await s.execute(select(Chat).where(Chat.accepted_at >= s0, Chat.accepted_at < s1,
                                                   Chat.operator_id.is_not(None)))).scalars().all()
        accepted = (await s.execute(select(Lead.accepted_by_id, func.count(Lead.id))
                                    .where(Lead.accepted_at >= s0, Lead.accepted_at < s1, Lead.accepted_by_id.is_not(None))
                                    .group_by(Lead.accepted_by_id))).all()
        msgs = (await s.execute(select(Message.staff_id, func.count(Message.id))
                                .where(Message.sender == "operator", Message.created_at >= s0, Message.created_at < s1)
                                .group_by(Message.staff_id))).all()
        actions = (await s.execute(select(AuditLog.staff_id, func.count(AuditLog.id))
                                   .where(AuditLog.created_at >= s0, AuditLog.created_at < s1, AuditLog.action == "lead_status")
                                   .group_by(AuditLog.staff_id))).all()
    acc_map = dict(accepted)
    msg_map = dict(msgs)
    act_map = dict(actions)
    by_op: dict[int, list[Chat]] = defaultdict(list)
    for c in chats:
        by_op[c.operator_id].append(c)
    out = []
    for st in staff:
        cs = by_op.get(st.id, [])
        first = [(c.first_response_at - c.accepted_at).total_seconds() for c in cs if c.first_response_at and c.accepted_at]
        wait = [max(0.0, (c.accepted_at - c.sla_start).total_seconds()) for c in cs if c.accepted_at and c.sla_start]
        dur = [(c.closed_at - c.accepted_at).total_seconds() for c in cs if c.closed_at and c.accepted_at]
        ratings = [c.rating for c in cs if c.rating]
        acc = acc_map.get(st.id, 0)
        out.append({
            "id": st.id, "name": st.full_name, "display": st.display_name, "role": st.role, "active": st.is_active,
            "chats": len(cs), "closed": sum(1 for c in cs if c.status == "closed"),
            "open": sum(1 for c in cs if c.status == "active"),
            "avg_first_response": _avg(first), "avg_wait": _avg(wait), "avg_duration": _avg(dur),
            "avg_rating": round(_avg(ratings), 2) if ratings else None, "ratings": len(ratings),
            "low_ratings": sum(1 for r in ratings if r <= 2),
            "accepted": acc, "conv": round(acc / len(cs) * 100, 1) if cs else 0,
            "messages": msg_map.get(st.id, 0), "status_changes": act_map.get(st.id, 0),
            "transfers": sum(c.transfers or 0 for c in cs),
        })
    return out


async def operator_series(start: date, end: date, monthly: bool = False) -> dict:
    """Operatorlar kesimida chatlar soni (grafik uchun)."""
    s0, s1 = range_utc(start, end)
    async with session_scope() as s:
        staff = {x.id: x.display_name for x in (await s.execute(select(Staff))).scalars().all()}
        rows = (await s.execute(select(Chat.operator_id, Chat.accepted_at)
                                .where(Chat.accepted_at >= s0, Chat.accepted_at < s1, Chat.operator_id.is_not(None)))).all()
    if monthly:
        keys = sorted({worktime.to_local(a).strftime("%Y-%m") for _, a in rows}) or [start.strftime("%Y-%m")]
        labels = keys
        keyf = lambda d: worktime.to_local(d).strftime("%Y-%m")  # noqa: E731
    else:
        days = day_range(start, end)
        keys = [d.isoformat() for d in days]
        labels = [d.strftime("%d.%m") for d in days]
        keyf = lambda d: _local_date(d).isoformat()  # noqa: E731
    per: dict[int, Counter] = defaultdict(Counter)
    for op, acc in rows:
        per[op][keyf(acc)] += 1
    datasets = [{"label": staff.get(op, f"#{op}"), "data": [cnt.get(k, 0) for k in keys]} for op, cnt in per.items()]
    return {"labels": labels, "datasets": datasets}


def human_seconds(sec: float | None) -> str:
    if sec is None:
        return "—"
    sec = int(sec)
    if sec < 60:
        return f"{sec} s"
    if sec < 3600:
        return f"{sec // 60} daq {sec % 60} s"
    return f"{sec // 3600} soat {(sec % 3600) // 60} daq"
