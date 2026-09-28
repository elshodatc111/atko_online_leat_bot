"""Boshlang'ich ma'lumotlar (birinchi ishga tushirishda bir marta yoziladi)."""
from __future__ import annotations

from sqlalchemy import func, select

from .config import config
from .db import session_scope
from .models import InfoPage, ReminderStep, Source, Staff, Tariff, Template

TARIFFS = [
    ("group", "1-tarif: Self-Study + AI & Community", "Тариф 1: Self-Study + AI & Community",
     "• Yopiq Telegram guruhida video darslar\n• Oyiga 4 marta o'qituvchi bilan qo'shimcha jonli dars\n• AI Telegram bot 24/7 savollarga javob beradi, guruhga biriktirilgan Mentor ham yordam beradi\n• Har hafta bot orqali daraja bo'yicha test. Sovrinlar: 1-o'rin — keyingi oy BEPUL, 2-3-o'rin — keyingi oyga 50% chegirma\n• Barcha o'quv materiallari va PDF fayllar BEPUL\n\n👉 Kimga mos: vaqti kam, mustaqil o'qiy oladigan, qulay narxdagi yo'l izlayotganlar.",
     "• Видеоуроки в закрытой Telegram-группе\n• 4 раза в месяц дополнительный живой урок с преподавателем\n• AI Telegram-бот отвечает на вопросы 24/7, также помогает закреплённый ментор\n• Еженедельный тест по уровню через бота. Призы: 1-е место — следующий месяц БЕСПЛАТНО, 2-3 места — скидка 50% на следующий месяц\n• Все учебные материалы и PDF — БЕСПЛАТНО\n\n👉 Кому подходит: тем, у кого мало времени, кто может учиться самостоятельно и ищет доступный вариант."),
    ("group", "2-tarif: Interactive Group", "Тариф 2: Interactive Group",
     "• Zoom yoki Google Meet orqali jonli darslar\n• Haftada 3 kun, 2 soatdan\n• Guruhlar darajaga qarab ajratiladi\n• AI Telegram bot va shaxsiy Mentor bilan doimiy aloqa\n• Barcha o'quv materiallari va PDF fayllar BEPUL\n\n👉 Kimga mos: jonli dars va intizom kerak bo'lganlar, ayniqsa noldan boshlovchilar.",
     "• Живые уроки через Zoom или Google Meet\n• 3 раза в неделю по 2 часа\n• Группы формируются по уровню\n• Постоянная связь с AI-ботом и личным ментором\n• Все учебные материалы и PDF — БЕСПЛАТНО\n\n👉 Кому подходит: тем, кому нужны живые уроки и дисциплина, особенно начинающим с нуля."),
    ("group", "3-tarif: Intensive VIP (guruh)", "Тариф 3: Intensive VIP (группа)",
     "• Zoom/Meet orqali intensiv jonli guruh darslari\n• Haftada 5 kun, 2 soatdan\n• Mentor bilan uzluksiz aloqa va shaxsiy nazorat\n• Barcha o'quv materiallari va PDF fayllar BEPUL\n\n👉 Kimga mos: imtihonga oz vaqt qolgan, tez natija kerak bo'lganlar.",
     "• Интенсивные живые групповые уроки через Zoom/Meet\n• 5 раз в неделю по 2 часа\n• Непрерывная связь с ментором и личный контроль\n• Все учебные материалы и PDF — БЕСПЛАТНО\n\n👉 Кому подходит: тем, у кого мало времени до экзамена и нужен быстрый результат."),
    ("individual", "Individual B (1-ga-1, haftasiga 2 kun)", "Individual B (1-на-1, 2 раза в неделю)",
     "• O'qituvchi bilan shaxsiy darslar, haftasiga 2 kun, 2 soatdan\n• Moslashuvchan grafik va shaxsiy dastur\n• Individual nazorat\n• Narx darajasi: individual VIP'ga nisbatan pastroq\n\n👉 Kimga mos: shaxsiy yondashuv kerak, lekin vaqti yoki byudjeti cheklanganlar.",
     "• Личные уроки с преподавателем, 2 раза в неделю по 2 часа\n• Гибкий график и индивидуальная программа\n• Индивидуальный контроль\n• Уровень цены: ниже, чем Individual VIP\n\n👉 Кому подходит: нужен личный подход, но ограничены время или бюджет."),
    ("individual", "Individual VIP (1-ga-1, haftasiga 5 kun)", "Individual VIP (1-на-1, 5 раз в неделю)",
     "• O'qituvchi bilan intensiv shaxsiy darslar, haftasiga 5 kun, 2 soatdan\n• Moslashuvchan grafik, shaxsiy dastur va individual nazorat\n• Eng tez natija\n\n👉 Kimga mos: eng tez natija va intensiv shaxsiy tayyorgarlik kerak bo'lganlar.",
     "• Интенсивные личные уроки, 5 раз в неделю по 2 часа\n• Гибкий график, индивидуальная программа и контроль\n• Самый быстрый результат\n\n👉 Кому подходит: нужен максимально быстрый результат и интенсивная личная подготовка."),
    ("hybrid", "Gibrid 1: Video + Offline muloqot", "Гибрид 1: Видео + офлайн-практика",
     "• Video darslarni platforma va bot orqali ko'rasiz\n• Haftada 1 marta ATKO markazida amaliyot va so'zlashuv mashg'uloti",
     "• Видеоуроки на платформе и в боте\n• 1 раз в неделю практика и разговорное занятие в центре ATKO"),
    ("hybrid", "Gibrid 2: Offline dars + Online AI Mentor", "Гибрид 2: Офлайн-уроки + онлайн AI-ментор",
     "• Darslar ATKO markazida\n• Uyga vazifa, testlar va 24/7 savol-javob — AI bot va online mentor orqali",
     "• Уроки в центре ATKO\n• Домашние задания, тесты и вопросы 24/7 — через AI-бота и онлайн-ментора"),
    ("hybrid", "Gibrid 3: Zoom dars + Offline Master-klass/Exam", "Гибрид 3: Zoom-уроки + офлайн мастер-класс/экзамен",
     "• Online Zoom guruhlarida o'qish\n• Oyiga 1 marta ATKO markazida MOCK-TOPIK imtihoni\n• Jonli Speaking Club'larda qatnashish",
     "• Обучение в онлайн-группах Zoom\n• Раз в месяц MOCK-TOPIK в центре ATKO\n• Участие в живых Speaking Club"),
]

INFO_PAGES = [
    ("about", "ATKO haqida va aloqa", "Об ATKO и контакты",
     "ATKO — koreys tili, TOPIK va EPS-TOPIK imtihonlariga tayyorlovchi professional o'quv markazi. Ta'lim shakllari: online, offline va gibrid.\n\n📍 Manzil: [TO'LDIRILSIN]\n🗺 Mo'ljal: [TO'LDIRILSIN]\n📞 Telefon: [TO'LDIRILSIN]\n📢 Telegram kanal / Instagram: [TO'LDIRILSIN]",
     "ATKO — профессиональный учебный центр подготовки к корейскому языку, экзаменам TOPIK и EPS-TOPIK. Форматы обучения: онлайн, офлайн и гибрид.\n\n📍 Адрес: [TO'LDIRILSIN]\n🗺 Ориентир: [TO'LDIRILSIN]\n📞 Телефон: [TO'LDIRILSIN]\n📢 Telegram-канал / Instagram: [TO'LDIRILSIN]", True, 1),
    ("free", "Bepul imkoniyatlar", "Бесплатные возможности",
     "🎁 Birinchi (sinov) dars — mutlaqo BEPUL\n📄 Bepul PDF darsliklar va koreys tili lug'atlari\n📊 TOPIK va EPS-TOPIK testlari tahlili",
     "🎁 Первый (пробный) урок — абсолютно БЕСПЛАТНО\n📄 Бесплатные PDF-учебники и словари корейского языка\n📊 Разбор тестов TOPIK и EPS-TOPIK", True, 2),
    ("exams", "TOPIK va EPS-TOPIK haqida", "О TOPIK и EPS-TOPIK",
     "TOPIK I (1-2 daraja): tinglab tushunish + o'qish, jami 200 ball. 1-daraja — 80+, 2-daraja — 140+.\nTOPIK II (3-6 daraja): tinglab tushunish + yozish + o'qish, jami 300 ball. 3-daraja — 120+, 4 — 150+, 5 — 190+, 6 — 230+.\nNatija 2 yil amal qiladi.\n\nEPS-TOPIK — Koreyaga EPS dasturi orqali ishga borish uchun topshiriladigan imtihon (o'qish + tinglab tushunish). Ro'yxatdan o'tish va ishga yuborish faqat rasmiy davlat idorasi orqali amalga oshiriladi. ATKO faqat imtihonga tayyorlaydi, ish yoki vizani kafolatlamaydi.\n\nO'zbekistondagi imtihon sanalari: [TO'LDIRILSIN]",
     "TOPIK I (1-2 уровень): аудирование + чтение, всего 200 баллов. 1 уровень — 80+, 2 уровень — 140+.\nTOPIK II (3-6 уровень): аудирование + письмо + чтение, всего 300 баллов. 3 уровень — 120+, 4 — 150+, 5 — 190+, 6 — 230+.\nРезультат действует 2 года.\n\nEPS-TOPIK — экзамен для трудоустройства в Корее по программе EPS (чтение + аудирование). Регистрация и направление на работу — только через официальный государственный орган. ATKO только готовит к экзамену и не гарантирует работу или визу.\n\nДаты экзаменов в Узбекистане: [TO'LDIRILSIN]", True, 3),
    ("organization", "Tashkiliy ma'lumotlar", "Организационная информация",
     "Kurs davomiyligi: [TO'LDIRILSIN]\nDars jadvallari: [TO'LDIRILSIN]\nO'qituvchilar: [TO'LDIRILSIN]\nGuruh hajmi: [TO'LDIRILSIN]\nTo'lov usullari: [TO'LDIRILSIN]\nQaytarish siyosati: [TO'LDIRILSIN]\nDars qoldirilsa: [TO'LDIRILSIN]\nSertifikat: [TO'LDIRILSIN]\nDaraja aniqlash testi: [TO'LDIRILSIN]",
     "Длительность курса: [TO'LDIRILSIN]\nРасписание: [TO'LDIRILSIN]\nПреподаватели: [TO'LDIRILSIN]\nРазмер группы: [TO'LDIRILSIN]\nСпособы оплаты: [TO'LDIRILSIN]\nПолитика возврата: [TO'LDIRILSIN]\nПропуск урока: [TO'LDIRILSIN]\nСертификат: [TO'LDIRILSIN]\nТест на уровень: [TO'LDIRILSIN]", False, 4),
]

REMINDERS = [
    (1, "📄 Salom! Koreys tilini o'rganishni boshlash uchun sizga bepul materiallarimiz tayyor. Menyudagi «📄 Bepul materiallar» bo'limiga kiring!\n\n🎁 Bepul 1-darsga yozilishni ham unutmang.",
        "📄 Здравствуйте! Для старта изучения корейского мы подготовили бесплатные материалы. Загляните в раздел «📄 Бесплатные материалы»!\n\n🎁 И не забудьте записаться на бесплатный 1-й урок."),
    (3, "📊 Bilasizmi? TOPIK I da 2-daraja uchun 200 balldan 140 ball kerak. Biz sizga TOPIK / EPS-TOPIK testlarining bepul tahlilini qilib beramiz!\n\nBoshlash uchun «👨‍💼 Operator bilan bog'lanish» tugmasini bosing.",
        "📊 Знаете ли вы? Для 2 уровня TOPIK I нужно 140 из 200 баллов. Мы бесплатно разберём с вами тесты TOPIK / EPS-TOPIK!\n\nНажмите «👨‍💼 Связаться с оператором», чтобы начать."),
    (7, "🇰🇷 Koreys tilini o'rganishni kechiktirmang! Bepul 1-darsda darajangizni aniqlaymiz va sizga mos tarifni tanlab beramiz.\n\n«🎁 Bepul 1-dars» tugmasini bosing — menejerimiz siz bilan bog'lanadi.",
        "🇰🇷 Не откладывайте изучение корейского! На бесплатном 1-м уроке определим ваш уровень и подберём подходящий тариф.\n\nНажмите «🎁 Бесплатный 1-й урок» — менеджер свяжется с вами."),
]

TEMPLATES = [
    ("Bepul dars taklifi",
     "Sizni bepul 1-darsimizga taklif qilamiz! 🎁 Sizga qaysi kun va vaqt qulay?",
     "Приглашаем вас на бесплатный 1-й урок! 🎁 Какой день и время вам удобны?"),
    ("Narx haqida",
     "Narx siz tanlagan tarif va darajangizga qarab individual hisoblanadi, hozirda maxsus chegirmalarimiz ham bor. Qaysi tarif sizni ko'proq qiziqtiryapti?",
     "Стоимость рассчитывается индивидуально по тарифу и уровню, сейчас действуют специальные скидки. Какой тариф вас больше интересует?"),
    ("Qo'ng'iroq qilamiz",
     "Batafsil ma'lumot berish uchun sizga qo'ng'iroq qilsak bo'ladimi? Qaysi vaqt qulay?",
     "Можно вам позвонить, чтобы рассказать подробнее? Какое время удобно?"),
    ("Rahmat",
     "Murojaatingiz uchun rahmat! Yana savollaringiz bo'lsa, bemalol yozing. 😊",
     "Спасибо за обращение! Если появятся вопросы — пишите. 😊"),
]

SOURCES = [("instagram", "Instagram"), ("telegram", "Telegram kanal"), ("facebook", "Facebook")]


async def seed() -> None:
    async with session_scope() as s:
        if (await s.execute(select(func.count(Tariff.id)))).scalar_one() == 0:
            for i, (cat, nu, nr, du, dr) in enumerate(TARIFFS):
                s.add(Tariff(category=cat, name_uz=nu, name_ru=nr, desc_uz=du, desc_ru=dr, sort=i))
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
