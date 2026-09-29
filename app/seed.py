"""Boshlang'ich ma'lumotlar (birinchi ishga tushirishda bir marta yoziladi)."""
from __future__ import annotations

from sqlalchemy import func, select

from .config import config
from .db import session_scope
from .models import ReminderStep, Source, Staff, SubscriptionPlan, Tariff

# (kategoriya, obunami, nom, tavsif) — tavsif botda oddiy matn sifatida ko'rsatiladi
TARIFFS = [
    ("subscription", True, "Premium video darslar (yopiq Telegram guruh)",
     "🎬 Koreys tilini o'zingizga qulay vaqtda, telefoningizdan o'rganing!\n\n"
     "Yopiq Telegram guruhda — noldan natijagacha to'liq video darslar:\n"
     "• 한글 Hangul alifbosi — noldan boshlash\n"
     "• 🎯 EPS-TOPIK 960, 600, 60 va 50 — to'liq kurslar\n"
     "• 📚 Kitoblar va qo'llanmalar\n"
     "• 🎧 Audio darslar (tinglab tushunish)\n"
     "• ⁉️ Testlar va 🎞 koreys kinolari\n"
     "• 🏆 Shogirdlarimiz natijalari\n\n"
     "🎁 Bonus: 🎓 AI mentor — 24/7 cheksiz savol-javob, uyga vazifani tekshirish va mini-testlar.\n\n"
     "✅ Payme orqali bir necha daqiqada to'lov — guruh havolasi darhol keladi.\n"
     "📅 Obuna muddati: 1 oy, 3 oy yoki 12 oy — pastdan tanlang 👇"),
    ("group", False, "Zoom — ustoz bilan guruh darslari",
     "🎥 Ustoz bilan jonli online darslar — uydan chiqmasdan!\n\n"
     "✅ Zoom orqali jonli guruh darslari: savol berasiz — ustoz darhol tushuntiradi\n"
     "📦 12 dars (haftasiga 3 ta) yoki 20 dars (haftasiga 5 ta) — 1 oy\n"
     "⏱ Har bir dars 120 daqiqa\n"
     "👥 Guruhlar darajangizga qarab tuziladi — noldan boshlovchilar uchun ham\n"
     "🎯 TOPIK, EPS-TOPIK yoki so'zlashuv — maqsadingizga mos dastur\n\n"
     "💳 To'lov oldindan, menejer orqali. Paketni tanlang — menejerimiz guruh va dars jadvalini siz bilan kelishib oladi 👇"),
    ("individual", False, "Individual — ustoz bilan yakkama-yakka (Zoom)",
     "👤 Ustoz bilan yakkama-yakka — tezroq natija uchun!\n\n"
     "✅ Darslar faqat siz uchun: darajangiz, tempingiz va maqsadingizga moslashtirilgan shaxsiy dastur\n"
     "📦 12 dars (haftasiga 3 ta) yoki 20 dars (haftasiga 5 ta) — 1 oy\n"
     "⏱ Har bir dars 120 daqiqa, Zoom orqali\n"
     "🗓 Dars vaqtini o'zingizga qulay qilib tanlaysiz\n"
     "🎯 Imtihonga qisqa muddatda tayyorlanmoqchi bo'lganlar uchun ayni muddao\n\n"
     "💳 To'lov oldindan, menejer orqali. Paketni tanlang — menejerimiz qulay vaqtni siz bilan kelishib oladi 👇"),
]

PLANS = [("1 oy", 30), ("3 oy", 90), ("12 oy", 365)]

# kurs paketlari: kategoriya → [(darslar, haftasiga, oy, narx)]
OPTIONS = {
    "group": [(12, 3, 1, 599_000), (20, 5, 1, 949_000)],
    "individual": [(12, 3, 1, 1_490_000), (20, 5, 1, 2_390_000)],
}

REMINDERS = [
    (1, "👋 Salom! Koreys tilini o'rganishni boshlashga tayyormisiz? 🇰🇷\n\n"
        "Sizga mos yo'nalishni tanlang:\n"
        "💎 <b>Premium video darslar</b> — o'zingizga qulay vaqtda, yopiq Telegram guruhda\n"
        "🎥 <b>Zoom guruh darslari</b> — ustoz bilan jonli\n"
        "👤 <b>Individual darslar</b> — yakkama-yakka, shaxsiy dastur\n\n"
        "🤔 Qaysi biri sizga mosligini bilmayapsizmi? Maqsadingizni shu yerga yozing — tavsiya beramiz!\n"
        "👇 Yoki narxlarni hoziroq ko'ring."),
    (3, "🎓 Bilasizmi? Botimizda <b>AI mentor</b> bor — koreys tili bo'yicha savolingizga soniyalar ichida javob beradi va uyga vazifangizni tekshiradi.\n\n"
        "📝 Darajangizni bilmoqchimisiz? Bosh sahifadagi <b>«📝 Mini-test»</b>ni sinab ko'ring!\n\n"
        "💎 Premium obunachilar uchun AI mentor — <b>cheksiz</b>. Batafsil ma'lumot uchun pastdagi tugmani bosing 👇"),
    (7, "🇰🇷 Koreys tilini o'rganish rejangiz hali ham kuchdami?\n\n"
        "Har kuni atigi 30 daqiqa ham natija beradi — eng muhimi, bugun boshlash. 💪\n\n"
        "👨‍💼 Menejerimiz maqsadingiz va vaqtingizga qarab mos kurs va jadvalni tanlab beradi.\n"
        "👇 Pastdagi tugmani bosing yoki shu yerga <b>«Qo'ng'iroq qiling»</b> deb yozing — o'zimiz bog'lanamiz! 📞"),
]

SOURCES = [("instagram", "Instagram"), ("telegram", "Telegram kanal"), ("facebook", "Facebook")]


async def _insert_tariffs(s, only_courses: bool = False) -> None:
    from .models import TariffOption

    for i, (cat, is_sub, name, desc) in enumerate(TARIFFS):
        if only_courses and is_sub:
            continue
        tr = Tariff(category=cat, is_subscription=is_sub, name_uz=name, desc_uz=desc, sort=i, price=0, price_period="")
        s.add(tr)
        await s.flush()
        if is_sub:
            for j, (title, days) in enumerate(PLANS):
                s.add(SubscriptionPlan(tariff_id=tr.id, title_uz=title, days=days, price=0, sort=j))
        for j, (lessons, per_week, months, price) in enumerate(OPTIONS.get(cat, []) if not is_sub else []):
            s.add(TariffOption(tariff_id=tr.id, lessons=lessons, per_week=per_week, months=months, price=price, sort=j))


# v4: olib tashlangan bo'limlar jadvallari (bolalari oldin)
DROPPED_TABLES = ["group_post_deliveries", "group_posts", "channel_insights", "channel_invites", "channel_posts", "chat_stats",
                  "tg_chats", "promo_uses", "promo_codes", "faq_suggestions", "faq", "user_questions", "templates",
                  "info_pages", "material_chunks", "materials"]
# v4 da mazmuni o'zgargan bot matnlari — eski tahrirlar o'chiriladi
CHANGED_TEXTS = ("price_note", "enroll_request_ok", "choose_package", "buy_unavailable", "welcome", "ask_name", "tutor_intro")


async def migrate_v4() -> None:
    """v3 → v4 (soddalashtirish): kanal, o'quv guruhlari, postlar, promokodlar, FAQ, shablonlar, markaz sahifalari va
    PDF materiallar olib tashlandi; bot faqat o'zbek tilida. Eski ma'lumotlar butunlay tozalanadi."""
    import shutil

    from sqlalchemy import text

    from .db import engine
    from .services import settings as st

    if await st.get("schema_v4_done"):
        return
    async with engine.connect() as conn:
        # jadvallarni qayta qurishda FK tekshiruvi o'chiq bo'lishi kerak (tranzaksiyadan tashqarida)
        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for name in DROPPED_TABLES:
            await conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{name}"')
        # reminder_steps.material_id (materials jadvaliga FK) — jadvalni ustunsiz qayta quramiz
        cols = [r[1] for r in (await conn.exec_driver_sql("PRAGMA table_info(reminder_steps)")).fetchall()]
        if "material_id" in cols:
            await conn.exec_driver_sql(
                "CREATE TABLE reminder_steps_v4 (id INTEGER NOT NULL PRIMARY KEY, day_offset INTEGER NOT NULL, "
                "text_uz TEXT NOT NULL, text_ru TEXT NOT NULL DEFAULT '', is_active BOOLEAN NOT NULL DEFAULT 1)")
            await conn.exec_driver_sql("INSERT INTO reminder_steps_v4 (id, day_offset, text_uz, text_ru, is_active) "
                                       "SELECT id, day_offset, text_uz, '', is_active FROM reminder_steps")
            await conn.exec_driver_sql("DROP TABLE reminder_steps")
            await conn.exec_driver_sql("ALTER TABLE reminder_steps_v4 RENAME TO reminder_steps")
        # faqat o'zbek tili: barcha leadlar uz, ruscha matnlar tozalanadi
        await conn.execute(text("UPDATE leads SET lang='uz'"))
        await conn.execute(text("UPDATE leads SET pending_input=NULL WHERE pending_input='promo'"))
        await conn.execute(text("UPDATE leads SET onboarding_step='name' WHERE onboarding_step='lang'"))
        await conn.execute(text("UPDATE tariffs SET name_ru='', desc_ru=''"))
        await conn.execute(text("UPDATE subscription_plans SET title_ru=''"))
        await conn.execute(text("UPDATE reminder_steps SET text_ru=''"))
        await conn.execute(text("UPDATE tariffs SET desc_uz=REPLACE(desc_uz, 'To''lov oldindan, admin orqali', 'To''lov oldindan, menejer orqali')"))
        await conn.commit()
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.commit()
    # sozlamalar: eskirgan kalitlar va ruscha / o'zgargan matn tahrirlari
    async with engine.begin() as conn:
        for k in st.OBSOLETE_KEYS:
            await conn.execute(text("DELETE FROM settings WHERE key=:k"), {"k": k})
    texts = {}
    for k, v in dict(await st.get("texts") or {}).items():
        if k in CHANGED_TEXTS or not isinstance(v, dict) or not v.get("uz"):
            continue
        texts[k] = {"uz": v["uz"]}
    await st.load()
    await st.set_many({"texts": texts, "known_chats": {cid: info for cid, info in dict(await st.get("known_chats") or {}).items()
                                                       if isinstance(info, dict) and info.get("type") != "channel"},
                       "schema_v4_done": True})
    # olib tashlangan bo'limlarning fayllari (postlar rasmi/videosi, PDF materiallar)
    from .config import config

    for sub in ("posts", "materials"):
        shutil.rmtree(config.media_dir() / sub, ignore_errors=True)
    import logging

    logging.getLogger("atko").info("v4 migratsiya: eski bo'limlar jadvallari va ma'lumotlari tozalandi")


# v4.4: tarif tavsiflari va eslatmalar qayta yozildi — faqat admin o'zgartirmagan (eski standart) matnlar almashtiriladi
OLD_TARIFF_DESCS = [
    "📹 Yopiq Telegram guruhda to'liq video darslar to'plami:\n• 한글 Hangul alifbosi\n• EPS-TOPIK 960, 600, 60, 50 — to'liq kurslar\n• 📚 Kitoblar va qo'llanmalar\n• 🎵 Audio materiallar\n• ⁉️ Testlar\n• 🎬 Koreys kinolari\n• 🏆 Shogirdlarimiz natijalari\n\n💎 Premium obunachilar 🎓 AI mentordan cheksiz foydalanadi.\n📅 Obuna: 1 oy, 3 oy yoki 12 oy. To'lov Payme orqali, guruhga avtomatik qo'shilasiz.",
    "🎥 Zoom orqali ustoz bilan jonli online guruh darslari\n📦 12 dars (haftasiga 3 ta) yoki 20 dars (haftasiga 5 ta) — davomiyligi 1 oy\n⏱ Har bir dars 120 daqiqa\n👥 Guruhlar darajaga qarab ajratiladi\n💳 To'lov oldindan, menejer orqali",
    "👤 Zoom orqali ustoz bilan yakkama-yakka shaxsiy darslar\n📦 12 dars (haftasiga 3 ta) yoki 20 dars (haftasiga 5 ta) — davomiyligi 1 oy\n⏱ Har bir dars 120 daqiqa\n🗓 Moslashuvchan grafik va shaxsiy dastur\n💳 To'lov oldindan, menejer orqali"
]
OLD_REMINDERS = [
    "📚 Salom! ATKO tariflari bilan tanishdingizmi?\n\n💎 <b>Premium video darslar</b> — yopiq Telegram guruhda Hangul, EPS-TOPIK 960/600, kitoblar, audio va testlar. Obuna 1 oydan boshlanadi.\n\n«📚 Tariflar va narxlar» bo'limini oching 👇",
    "🎓 Koreys tilidagi savollaringizga <b>AI mentor</b> javob beradi: grammatika, uyga vazifani tekshirish, mini-testlar.\nPremium obunachilar uchun — cheksiz!\n\nMenyudagi «🎓 AI mentor» tugmasini bosing.",
    "🇰🇷 Koreys tilini o'rganishni kechiktirmang! Menejerlarimiz sizga mos tarifni tanlashda yordam beradi.\n\n«👨‍💼 Operator bilan bog'lanish» tugmasini bosing — batafsil ma'lumot beramiz."
]


async def migrate_content_v5() -> None:
    from .services import settings as st

    if await st.get("content_v5_done"):
        return
    new_desc = {cat: desc for cat, _, _, desc in TARIFFS}
    new_rem = dict(REMINDERS)
    async with session_scope() as s:
        for x in (await s.execute(select(Tariff))).scalars().all():
            if (x.desc_uz or "").strip() in [d.strip() for d in OLD_TARIFF_DESCS] and x.category in new_desc:
                x.desc_uz = new_desc[x.category]
            if x.name_uz == "1-tarif: Premium video darslar (yopiq Telegram guruh)":
                x.name_uz = "Premium video darslar (yopiq Telegram guruh)"
        for r in (await s.execute(select(ReminderStep))).scalars().all():
            if (r.text_uz or "").strip() in [t.strip() for t in OLD_REMINDERS] and r.day_offset in new_rem:
                r.text_uz = new_rem[r.day_offset]
    await st.set_value("content_v5_done", True)


async def migrate_texts_v5() -> None:
    """Bot matnlari to'liq qayta yozildi — paneldagi eski tahrirlar bir marta tozalanadi (yangi matnlar ko'rinishi uchun)."""
    from .services import settings as st

    if await st.get("texts_v5_done"):
        return
    await st.set_many({"texts": {}, "texts_v5_done": True})


async def migrate_v3b() -> None:
    """v3.1: Individual darslar ham Zoom orqali (120 daqiqa) — tavsif va nom (admin o'zgartirmagan bo'lsa)."""
    from .services import settings as st

    if await st.get("schema_v3b_done"):
        return
    pairs = [("👤 Ustoz bilan yakkama-yakka shaxsiy darslar", "👤 Zoom orqali ustoz bilan yakkama-yakka shaxsiy darslar")]
    async with session_scope() as s:
        for x in (await s.execute(select(Tariff).where(Tariff.category == "individual"))).scalars().all():
            for a, b in pairs:
                if x.desc_uz.startswith(a):
                    x.desc_uz = x.desc_uz.replace(a, b, 1)
            if x.name_uz == "Individual — ustoz bilan yakkama-yakka":
                x.name_uz = "Individual — ustoz bilan yakkama-yakka (Zoom)"
    await st.set_value("schema_v3b_done", True)


async def migrate_v3() -> None:
    """v2 → v3: Zoom (12/20 dars) va Individual (12/20 dars) paketli tariflar; eski 2–4-tariflar o'rniga."""
    from .services import settings as st

    if await st.get("schema_v3_done"):
        return
    from .models import TariffOption

    async with session_scope() as s:
        if (await s.execute(select(func.count(TariffOption.id)))).scalar_one():
            await st.set_value("schema_v3_done", True)  # yangi baza — paketlar allaqachon yozilgan
            return
    async with session_scope() as s:
        for x in (await s.execute(select(Tariff).where(Tariff.is_subscription.is_(False)))).scalars().all():
            await s.delete(x)
        await s.flush()
        await _insert_tariffs(s, only_courses=True)
    await st.set_value("schema_v3_done", True)


async def migrate_v2() -> None:
    """v1 → v2: yangi 4 ta tarif, bepul dars/materiallarni olib tashlash, yangi eslatmalar."""
    from .services import settings as st

    if await st.get("schema_v2_done"):
        return
    async with session_scope() as s:
        has_sub = (await s.execute(select(func.count(Tariff.id)).where(Tariff.is_subscription.is_(True)))).scalar_one()
        if not has_sub:
            for x in (await s.execute(select(Tariff))).scalars().all():
                await s.delete(x)
            await s.flush()
            await _insert_tariffs(s)
        old = (await s.execute(select(ReminderStep))).scalars().all()
        if any("bepul" in (r.text_uz or "").lower() for r in old):
            for r in old:
                await s.delete(r)
            await s.flush()
            for day, text in REMINDERS:
                s.add(ReminderStep(day_offset=day, text_uz=text))
    # mazmuni o'zgargan matnlar bo'yicha eski tahrirlarni tozalaymiz
    texts = dict(await st.get("texts") or {})
    for key in ("ask_phone", "welcome", "chat_closed", "rating_ask", "tutor_intro", "tutor_limit", "operator_connected"):
        texts.pop(key, None)
    await st.set_many({"texts": texts, "tutor_trial_daily": 3, "schema_v2_done": True})


async def seed() -> None:
    async with session_scope() as s:
        fresh = (await s.execute(select(func.count(Tariff.id)))).scalar_one() == 0
        if fresh:
            await _insert_tariffs(s)
        if (await s.execute(select(func.count(ReminderStep.id)))).scalar_one() == 0:
            for day, text in REMINDERS:
                s.add(ReminderStep(day_offset=day, text_uz=text))
        if (await s.execute(select(func.count(Source.id)))).scalar_one() == 0:
            for code, name in SOURCES:
                s.add(Source(code=code, name=name))
        # .env dagi admin(lar)
        for tg_id in config.ADMIN_TG_IDS:
            st = (await s.execute(select(Staff).where(Staff.tg_id == tg_id))).scalars().first()
            if st is None:
                s.add(Staff(tg_id=tg_id, full_name="Administrator", display_name="ATKO Admin", role="admin"))
            elif st.role != "admin" or not st.is_active:
                st.role, st.is_active = "admin", True
