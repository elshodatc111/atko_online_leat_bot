"""Boshlang'ich ma'lumotlar (birinchi ishga tushirishda bir marta yoziladi)."""
from __future__ import annotations

from sqlalchemy import func, select

from .config import config
from .db import session_scope
from .models import InfoPage, ReminderStep, Source, Staff, SubscriptionPlan, Tariff, Template

# (kategoriya, obunami, nom_uz, nom_ru, tavsif_uz, tavsif_ru)
TARIFFS = [
    ("subscription", True, "1-tarif: Premium video darslar (yopiq Telegram guruh)", "Тариф 1: Premium видеоуроки (закрытая Telegram-группа)",
     "📹 Yopiq Telegram guruhda to'liq video darslar to'plami:\n• 한글 Hangul alifbosi\n• EPS-TOPIK 960, 600, 60, 50 — to'liq kurslar\n• 📚 Kitoblar va qo'llanmalar\n• 🎵 Audio materiallar\n• ⁉️ Testlar\n• 🎬 Koreys kinolari\n• 🏆 Shogirdlarimiz natijalari\n\n💎 Premium obunachilar 🎓 AI mentordan cheksiz foydalanadi.\n📅 Obuna: 1 oy, 3 oy yoki 12 oy. To'lov Payme orqali, guruhga avtomatik qo'shilasiz.",
     "📹 Полный набор видеоуроков в закрытой Telegram-группе:\n• 한글 Алфавит хангыль\n• EPS-TOPIK 960, 600, 60, 50 — полные курсы\n• 📚 Книги и пособия\n• 🎵 Аудиоматериалы\n• ⁉️ Тесты\n• 🎬 Корейские фильмы\n• 🏆 Результаты наших учеников\n\n💎 Premium-подписчики пользуются 🎓 AI-ментором без ограничений.\n📅 Подписка: 1, 3 или 12 месяцев. Оплата через Payme, вступление в группу автоматически."),
    ("group", False, "Zoom — ustoz bilan guruh darslari", "Zoom — групповые занятия с преподавателем",
     "🎥 Zoom orqali ustoz bilan jonli online guruh darslari\n📦 12 dars (haftasiga 3 ta) yoki 20 dars (haftasiga 5 ta) — davomiyligi 1 oy\n⏱ Har bir dars 120 daqiqa\n👥 Guruhlar darajaga qarab ajratiladi\n💳 To'lov oldindan, admin orqali",
     "🎥 Живые онлайн-занятия в группе с преподавателем через Zoom\n📦 12 уроков (3 раза в неделю) или 20 уроков (5 раз в неделю) — 1 месяц\n⏱ Каждый урок 120 минут\n👥 Группы формируются по уровню\n💳 Предоплата, через администратора"),
    ("individual", False, "Individual — ustoz bilan yakkama-yakka (Zoom)", "Индивидуально — один на один с преподавателем (Zoom)",
     "👤 Zoom orqali ustoz bilan yakkama-yakka shaxsiy darslar\n📦 12 dars (haftasiga 3 ta) yoki 20 dars (haftasiga 5 ta) — davomiyligi 1 oy\n⏱ Har bir dars 120 daqiqa\n🗓 Moslashuvchan grafik va shaxsiy dastur\n💳 To'lov oldindan, admin orqali",
     "👤 Личные занятия один на один с преподавателем через Zoom\n📦 12 уроков (3 раза в неделю) или 20 уроков (5 раз в неделю) — 1 месяц\n⏱ Каждый урок 120 минут\n🗓 Гибкий график и индивидуальная программа\n💳 Предоплата, через администратора"),
]

PLANS = [("1 oy", "1 месяц", 30), ("3 oy", "3 месяца", 90), ("12 oy", "12 месяцев", 365)]

# kurs paketlari: kategoriya → [(darslar, haftasiga, oy, narx)]
OPTIONS = {
    "group": [(12, 3, 1, 599_000), (20, 5, 1, 949_000)],
    "individual": [(12, 3, 1, 1_490_000), (20, 5, 1, 2_390_000)],
}

INFO_PAGES = [
    ("about", "ATKO haqida va aloqa", "Об ATKO и контакты",
     "ATKO — koreys tili, TOPIK va EPS-TOPIK imtihonlariga tayyorlovchi professional o'quv markazi. Ta'lim shakllari: online, offline va gibrid.\n\n📍 Manzil: [TO'LDIRILSIN]\n🗺 Mo'ljal: [TO'LDIRILSIN]\n📞 Telefon: [TO'LDIRILSIN]\n📢 Telegram kanal / Instagram: [TO'LDIRILSIN]",
     "ATKO — профессиональный учебный центр подготовки к корейскому языку, экзаменам TOPIK и EPS-TOPIK. Форматы обучения: онлайн, офлайн и гибрид.\n\n📍 Адрес: [TO'LDIRILSIN]\n🗺 Ориентир: [TO'LDIRILSIN]\n📞 Телефон: [TO'LDIRILSIN]\n📢 Telegram-канал / Instagram: [TO'LDIRILSIN]", True, 1),
    ("exams", "TOPIK va EPS-TOPIK haqida", "О TOPIK и EPS-TOPIK",
     "TOPIK I (1-2 daraja): tinglab tushunish + o'qish, jami 200 ball. 1-daraja — 80+, 2-daraja — 140+.\nTOPIK II (3-6 daraja): tinglab tushunish + yozish + o'qish, jami 300 ball. 3-daraja — 120+, 4 — 150+, 5 — 190+, 6 — 230+.\nNatija 2 yil amal qiladi.\n\nEPS-TOPIK — Koreyaga EPS dasturi orqali ishga borish uchun topshiriladigan imtihon (o'qish + tinglab tushunish). Ro'yxatdan o'tish va ishga yuborish faqat rasmiy davlat idorasi orqali amalga oshiriladi. ATKO faqat imtihonga tayyorlaydi, ish yoki vizani kafolatlamaydi.\n\nO'zbekistondagi imtihon sanalari: [TO'LDIRILSIN]",
     "TOPIK I (1-2 уровень): аудирование + чтение, всего 200 баллов. 1 уровень — 80+, 2 уровень — 140+.\nTOPIK II (3-6 уровень): аудирование + письмо + чтение, всего 300 баллов. 3 уровень — 120+, 4 — 150+, 5 — 190+, 6 — 230+.\nРезультат действует 2 года.\n\nEPS-TOPIK — экзамен для трудоустройства в Корее по программе EPS (чтение + аудирование). Регистрация и направление на работу — только через официальный государственный орган. ATKO только готовит к экзамену и не гарантирует работу или визу.\n\nДаты экзаменов в Узбекистане: [TO'LDIRILSIN]", True, 3),
    ("organization", "Tashkiliy ma'lumotlar", "Организационная информация",
     "Kurs davomiyligi: [TO'LDIRILSIN]\nDars jadvallari: [TO'LDIRILSIN]\nO'qituvchilar: [TO'LDIRILSIN]\nGuruh hajmi: [TO'LDIRILSIN]\nTo'lov usullari: [TO'LDIRILSIN]\nQaytarish siyosati: [TO'LDIRILSIN]\nDars qoldirilsa: [TO'LDIRILSIN]\nSertifikat: [TO'LDIRILSIN]\nDaraja aniqlash testi: [TO'LDIRILSIN]",
     "Длительность курса: [TO'LDIRILSIN]\nРасписание: [TO'LDIRILSIN]\nПреподаватели: [TO'LDIRILSIN]\nРазмер группы: [TO'LDIRILSIN]\nСпособы оплаты: [TO'LDIRILSIN]\nПолитика возврата: [TO'LDIRILSIN]\nПропуск урока: [TO'LDIRILSIN]\nСертификат: [TO'LDIRILSIN]\nТест на уровень: [TO'LDIRILSIN]", False, 4),
]

REMINDERS = [
    (1, "📚 Salom! ATKO tariflari bilan tanishdingizmi?\n\n💎 <b>Premium video darslar</b> — yopiq Telegram guruhda Hangul, EPS-TOPIK 960/600, kitoblar, audio va testlar. Obuna 1 oydan boshlanadi.\n\n«📚 Tariflar va narxlar» bo'limini oching 👇",
        "📚 Здравствуйте! Вы уже познакомились с тарифами ATKO?\n\n💎 <b>Premium видеоуроки</b> — закрытая Telegram-группа: хангыль, EPS-TOPIK 960/600, книги, аудио и тесты. Подписка от 1 месяца.\n\nОткройте раздел «📚 Тарифы и цены» 👇"),
    (3, "🎓 Koreys tilidagi savollaringizga <b>AI mentor</b> javob beradi: grammatika, uyga vazifani tekshirish, mini-testlar.\nPremium obunachilar uchun — cheksiz!\n\nMenyudagi «🎓 AI mentor» tugmasini bosing.",
        "🎓 На ваши вопросы по корейскому ответит <b>AI-ментор</b>: грамматика, проверка домашних заданий, мини-тесты.\nДля Premium-подписчиков — без ограничений!\n\nНажмите «🎓 AI-ментор» в меню."),
    (7, "🇰🇷 Koreys tilini o'rganishni kechiktirmang! Menejerlarimiz sizga mos tarifni tanlashda yordam beradi.\n\n«👨‍💼 Operator bilan bog'lanish» tugmasini bosing — batafsil ma'lumot beramiz.",
        "🇰🇷 Не откладывайте изучение корейского! Наши менеджеры помогут выбрать подходящий тариф.\n\nНажмите «👨‍💼 Связаться с оператором» — расскажем подробнее."),
]

TPL_TARIFFS_UZ = ("Bizda 3 yo'nalish bor: 💎 Premium video darslar (yopiq Telegram guruh, 1/3/12 oy), 🎥 Zoom — ustoz bilan guruh darslari "
                  "(12 dars — 599 000 so'm, 20 dars — 949 000 so'm) va 👤 Individual darslar (12 dars — 1 490 000 so'm, 20 dars — 2 390 000 so'm). "
                  "Qaysi biri sizni qiziqtiradi?")
TPL_TARIFFS_RU = ("У нас 3 направления: 💎 Premium видеоуроки (закрытая Telegram-группа, 1/3/12 мес.), 🎥 Zoom — групповые занятия с преподавателем "
                  "(12 уроков — 599 000 сум, 20 уроков — 949 000 сум) и 👤 индивидуальные занятия (12 уроков — 1 490 000 сум, 20 уроков — 2 390 000 сум). "
                  "Какой вас интересует?")
OLD_TPL_PREFIX = "Bizda 4 ta tarif bor"

TEMPLATES = [
    ("Tariflar haqida",
     TPL_TARIFFS_UZ,
     TPL_TARIFFS_RU),
    ("Narx haqida",
     "Narxlar botdagi «📚 Tariflar va narxlar» bo'limida ko'rsatilgan. Aniq narx va amaldagi chegirmalarni sizga hozir aytib beraman — qaysi tarif sizni qiziqtiryapti?",
     "Цены указаны в разделе «📚 Тарифы и цены». Точную стоимость и действующие скидки подскажу прямо сейчас — какой тариф вас интересует?"),
    ("Qo'ng'iroq qilamiz",
     "Batafsil ma'lumot berish uchun sizga qo'ng'iroq qilsak bo'ladimi? Qaysi vaqt qulay?",
     "Можно вам позвонить, чтобы рассказать подробнее? Какое время удобно?"),
    ("Rahmat",
     "Murojaatingiz uchun rahmat! Yana savollaringiz bo'lsa, bemalol yozing. 😊",
     "Спасибо за обращение! Если появятся вопросы — пишите. 😊"),
]

SOURCES = [("instagram", "Instagram"), ("telegram", "Telegram kanal"), ("facebook", "Facebook")]


async def _insert_tariffs(s, only_courses: bool = False) -> None:
    from .models import TariffOption

    for i, (cat, is_sub, nu, nr, du, dr) in enumerate(TARIFFS):
        if only_courses and is_sub:
            continue
        tr = Tariff(category=cat, is_subscription=is_sub, name_uz=nu, name_ru=nr, desc_uz=du, desc_ru=dr, sort=i,
                    price=0, price_period="")
        s.add(tr)
        await s.flush()
        if is_sub:
            for j, (tu, tr_ru, days) in enumerate(PLANS):
                s.add(SubscriptionPlan(tariff_id=tr.id, title_uz=tu, title_ru=tr_ru, days=days, price=0, sort=j))
        for j, (lessons, per_week, months, price) in enumerate(OPTIONS.get(cat, []) if not is_sub else []):
            s.add(TariffOption(tariff_id=tr.id, lessons=lessons, per_week=per_week, months=months, price=price, sort=j))


async def migrate_v3b() -> None:
    """v3.1: Individual darslar ham Zoom orqali (120 daqiqa) — tavsif va nom (admin o'zgartirmagan bo'lsa)."""
    from .services import settings as st

    if await st.get("schema_v3b_done"):
        return
    pairs = [("👤 Ustoz bilan yakkama-yakka shaxsiy darslar", "👤 Zoom orqali ustoz bilan yakkama-yakka shaxsiy darslar"),
             ("👤 Личные занятия один на один с преподавателем\n", "👤 Личные занятия один на один с преподавателем через Zoom\n")]
    async with session_scope() as s:
        for x in (await s.execute(select(Tariff).where(Tariff.category == "individual"))).scalars().all():
            for a, b in pairs:
                if x.desc_uz.startswith(a):
                    x.desc_uz = x.desc_uz.replace(a, b, 1)
                if x.desc_ru.startswith(a):
                    x.desc_ru = x.desc_ru.replace(a, b, 1)
            if x.name_uz == "Individual — ustoz bilan yakkama-yakka":
                x.name_uz = "Individual — ustoz bilan yakkama-yakka (Zoom)"
            if x.name_ru == "Индивидуально — один на один с преподавателем":
                x.name_ru = "Индивидуально — один на один с преподавателем (Zoom)"
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
        for tpl in (await s.execute(select(Template))).scalars().all():
            if (tpl.text_uz or "").startswith(OLD_TPL_PREFIX):
                tpl.text_uz, tpl.text_ru = TPL_TARIFFS_UZ, TPL_TARIFFS_RU
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
        for p in (await s.execute(select(InfoPage).where(InfoPage.key == "free"))).scalars().all():
            await s.delete(p)
        old = (await s.execute(select(ReminderStep))).scalars().all()
        if any("bepul" in (r.text_uz or "").lower() for r in old):
            for r in old:
                await s.delete(r)
            await s.flush()
            for day, tu, tr in REMINDERS:
                s.add(ReminderStep(day_offset=day, text_uz=tu, text_ru=tr))
        for tpl in (await s.execute(select(Template))).scalars().all():
            if "bepul" in (tpl.text_uz or "").lower() or "individual hisoblanadi" in (tpl.text_uz or ""):
                await s.delete(tpl)
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
        if (await s.execute(select(func.count(InfoPage.id)))).scalar_one() == 0:
            for key, tu, tr, bu, br, menu, sort in INFO_PAGES:
                s.add(InfoPage(key=key, title_uz=tu, title_ru=tr, body_uz=bu, body_ru=br, show_in_menu=menu, sort=sort))
        if (await s.execute(select(func.count(ReminderStep.id)))).scalar_one() == 0:
            for day, tu, tr in REMINDERS:
                s.add(ReminderStep(day_offset=day, text_uz=tu, text_ru=tr))
        if (await s.execute(select(func.count(Template.id)))).scalar_one() == 0:
            for i, (title, tu, tr) in enumerate(TEMPLATES):
                s.add(Template(title=title, text_uz=tu, text_ru=tr, sort=i))
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
