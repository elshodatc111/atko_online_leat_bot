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
    ("group", False, "2-tarif: Zoom guruh (haftada 3 kun)", "Тариф 2: Группа в Zoom (3 раза в неделю)",
     "🎥 Zoom orqali jonli online guruh darslari\n📅 Haftada 3 kun, har biri 2 soatdan\n👥 Guruhlar darajaga qarab ajratiladi\n💳 To'lov oldindan, admin orqali",
     "🎥 Живые онлайн-занятия в группе через Zoom\n📅 3 раза в неделю по 2 часа\n👥 Группы формируются по уровню\n💳 Предоплата, через администратора"),
    ("group", False, "3-tarif: Zoom intensiv (haftada 5 kun)", "Тариф 3: Интенсив в Zoom (5 раз в неделю)",
     "🔥 Zoom orqali jonli intensiv online darslar\n📅 Haftada 5 kun, har biri 2 soatdan\n🎯 Imtihonga tez tayyorlanish uchun\n💳 To'lov oldindan, admin orqali",
     "🔥 Живые интенсивные онлайн-занятия через Zoom\n📅 5 раз в неделю по 2 часа\n🎯 Для быстрой подготовки к экзамену\n💳 Предоплата, через администратора"),
    ("individual", False, "4-tarif: Individual (haftada 3 kun)", "Тариф 4: Индивидуально (3 раза в неделю)",
     "👤 O'qituvchi bilan 1-ga-1 shaxsiy darslar\n📅 Haftada 3 kun, har biri 2 soatdan\n🗓 Moslashuvchan grafik va shaxsiy dastur\n💳 To'lov oldindan, admin orqali",
     "👤 Личные занятия 1-на-1 с преподавателем\n📅 3 раза в неделю по 2 часа\n🗓 Гибкий график и индивидуальная программа\n💳 Предоплата, через администратора"),
]

PLANS = [("1 oy", "1 месяц", 30), ("3 oy", "3 месяца", 90), ("12 oy", "12 месяцев", 365)]

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

TEMPLATES = [
    ("Tariflar haqida",
     "Bizda 4 ta tarif bor: Premium video darslar (yopiq Telegram guruh), Zoom guruh (haftada 3 kun), Zoom intensiv (haftada 5 kun) va Individual darslar. Qaysi biri sizni qiziqtiradi?",
     "У нас 4 тарифа: Premium видеоуроки (закрытая Telegram-группа), группа в Zoom (3 раза в неделю), интенсив в Zoom (5 раз в неделю) и индивидуальные занятия. Какой вас интересует?"),
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


async def _insert_tariffs(s) -> None:
    for i, (cat, is_sub, nu, nr, du, dr) in enumerate(TARIFFS):
        tr = Tariff(category=cat, is_subscription=is_sub, name_uz=nu, name_ru=nr, desc_uz=du, desc_ru=dr, sort=i,
                    price=0, price_period="" if is_sub else "oyiga")
        s.add(tr)
        await s.flush()
        if is_sub:
            for j, (tu, tr_ru, days) in enumerate(PLANS):
                s.add(SubscriptionPlan(tariff_id=tr.id, title_uz=tu, title_ru=tr_ru, days=days, price=0, sort=j))


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
