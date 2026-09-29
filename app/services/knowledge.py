"""AI konsultant uchun bilimlar bazasi: faqat tariflar (narx va paketlar) va «Markaz haqida» matni.

AI mentor (tutor) esa darsliklarni OpenAI platformasidagi vector store (file_search) orqali ishlatadi — `ai.tutor_reply`.
"""
from __future__ import annotations

from sqlalchemy import select

from ..db import session_scope
from ..models import SubscriptionPlan, Tariff
from . import settings, worktime

CATEGORY_LABELS = {"subscription": "Obuna — yopiq Telegram guruh", "group": "Zoom guruh darslari",
                   "individual": "Individual (1-ga-1) darslar"}


async def course_knowledge(lang: str = "uz") -> str:
    """AI konsultant uchun bilimlar bazasi matni (o'zbekcha)."""
    from . import tariffs as tariff_svc

    async with session_scope() as s:
        tariffs = (await s.execute(select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort, Tariff.id))).scalars().all()
        plans = (await s.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True))
                                 .order_by(SubscriptionPlan.sort, SubscriptionPlan.days))).scalars().all()
    options = await tariff_svc.all_options()
    days_off = await settings.get("days_off") or []
    off_names = ", ".join(worktime.WEEKDAYS_UZ[d] for d in days_off) or "yo'q"

    parts: list[str] = []
    center = str(await settings.get("center_text") or "").strip()
    if center:
        parts.append("## MARKAZ HAQIDA\n" + center)
    parts.append("## OPERATORLAR ISH VAQTI\n"
                 f"{await worktime.work_hours_text()} (Toshkent vaqti). Dam olish: {off_names} va bayram kunlari.")
    parts.append("## TARIFLAR VA NARXLAR (so'mda)")
    for x in tariffs:
        if x.is_subscription:
            pl = [p for p in plans if p.tariff_id == x.id and p.price > 0]
            price = "; ".join(f"{p.title_uz} ({p.days} kun) — {tariff_svc.fmt_money(p.price)} so'm" for p in pl) or "narxni menejer aytadi"
            how = "Botda «📚 Tariflar va narxlar» → shu tarif → «💳 Sotib olish» orqali Payme bilan onlayn to'lanadi."
        else:
            opts = [o for o in options if o.tariff_id == x.id]
            if opts:
                price = "; ".join(
                    f"{tariff_svc.option_title(o)} ({tariff_svc.option_details(o)}) — "
                    + (f"{tariff_svc.fmt_money(o.price)} so'm (bir dars ≈ {tariff_svc.fmt_money(tariff_svc.per_lesson(o))} so'm)"
                       if o.price else "narxni menejer aytadi")
                    for o in opts)
            else:
                price = (f"{tariff_svc.fmt_money(x.price)} so'm" + (f" / {x.price_period}" if x.price_period else "")) if x.price else "narxni menejer aytadi"
            how = ("Oldindan to'lov, menejer orqali (Payme orqali emas). Botda tarif oynasida paketni tanlasa, "
                   "menejer bog'lanib to'lov va dars jadvalini kelishadi.")
        parts.append(f"### {x.name_uz}\n{x.desc_uz}\nNarx: {price}\nTo'lov: {how}")
    return "\n\n".join(parts)
