"""Bot matnlari (o'zbek va rus). EDITABLE ro'yxatidagilarni admin panelda o'zgartira oladi."""
from __future__ import annotations

from typing import Any

from ..services import settings as st

TEXTS: dict[str, dict[str, str]] = {
    # --- tahrirlanadigan matnlar
    "welcome": {
        "uz": "Assalomu alaykum! 👋\n<b>ATKO Koreys Tili O'quv Markazi</b>ga xush kelibsiz!\n\nBiz koreys tili, TOPIK va EPS-TOPIK imtihonlariga online, offline va gibrid formatda tayyorlaymiz. 🇰🇷",
        "ru": "Здравствуйте! 👋\nДобро пожаловать в <b>учебный центр корейского языка ATKO</b>!\n\nМы готовим к корейскому языку, экзаменам TOPIK и EPS-TOPIK в онлайн, офлайн и гибридном формате. 🇰🇷",
    },
    "ask_name": {
        "uz": "Tanishib olaylik 😊 Ismingiz nima?",
        "ru": "Давайте познакомимся 😊 Как вас зовут?",
    },
    "ask_phone": {
        "uz": "Rahmat, {name}! 📱 Menejerimiz siz bilan bog'lanishi va bepul 1-darsga taklif qilishi uchun pastdagi <b>«📱 Kontaktni ulashish»</b> tugmasini bosing.",
        "ru": "Спасибо, {name}! 📱 Чтобы менеджер связался с вами и пригласил на бесплатный 1-й урок, нажмите кнопку <b>«📱 Поделиться контактом»</b> ниже.",
    },
    "ask_goal": {
        "uz": "Koreys tilini qaysi maqsadda o'rganmoqchisiz?",
        "ru": "С какой целью вы хотите изучать корейский язык?",
    },
    "ask_format": {
        "uz": "Qaysi ta'lim formati sizga qulay?",
        "ru": "Какой формат обучения вам удобен?",
    },
    "onboarding_done": {
        "uz": "Ajoyib! ✅ Endi pastdagi menyudan kerakli bo'limni tanlang yoki savolingizni shunchaki yozing — men darhol javob beraman. 🤖",
        "ru": "Отлично! ✅ Теперь выберите раздел в меню ниже или просто напишите свой вопрос — я сразу отвечу. 🤖",
    },
    "operator_wait": {
        "uz": "✅ So'rovingiz qabul qilindi!\n👨‍💼 Operatorimiz <b>2–10 daqiqa</b> ichida chatga ulanadi. Savolingizni hozirdan yozib qoldirishingiz mumkin.",
        "ru": "✅ Ваш запрос принят!\n👨‍💼 Оператор подключится к чату в течение <b>2–10 минут</b>. Можете уже сейчас написать свой вопрос.",
    },
    "operator_off_hours": {
        "uz": "🌙 Hozir ish vaqtidan tashqari (operatorlar ish vaqti: <b>{hours}</b>, yakshanba va bayram kunlari dam olish).\n\n✅ So'rovingiz navbatga qo'yildi — operator <b>{next_open}</b> dan keyin siz bilan bog'lanadi.\n🤖 Ungacha savollaringizga AI-yordamchimiz javob beradi.",
        "ru": "🌙 Сейчас нерабочее время (операторы работают: <b>{hours}</b>, воскресенье и праздники — выходные).\n\n✅ Ваш запрос поставлен в очередь — оператор свяжется с вами после <b>{next_open}</b>.\n🤖 До этого на ваши вопросы ответит AI-помощник.",
    },
    "operator_connected": {
        "uz": "👨‍💼 Operator <b>{operator}</b> chatga ulandi. Savolingizni yozing!",
        "ru": "👨‍💼 Оператор <b>{operator}</b> подключился к чату. Задайте свой вопрос!",
    },
    "chat_closed": {
        "uz": "🔒 Chat yopildi.\nQo'shimcha savollaringiz bo'lsa, qayta murojaat qilishingiz mumkin! 😊\n\nHurmat bilan, {operator}\nATKO Koreys Tili O'quv Markazi",
        "ru": "🔒 Чат закрыт.\nЕсли у вас появятся вопросы, вы можете обратиться снова! 😊\n\nС уважением, {operator}\nУчебный центр корейского языка ATKO",
    },
    "rating_ask": {
        "uz": "⭐️ Iltimos, operatorimiz xizmatini baholang:",
        "ru": "⭐️ Пожалуйста, оцените работу нашего оператора:",
    },
    "rating_comment_ask": {
        "uz": "Rahmat! 🙏 Xohlasangiz, fikringizni yozib qoldiring (yoki «O'tkazib yuborish» tugmasini bosing):",
        "ru": "Спасибо! 🙏 Если хотите, напишите свой отзыв (или нажмите «Пропустить»):",
    },
    "rating_thanks": {
        "uz": "Fikringiz uchun katta rahmat! 💙 Bu bizga xizmatimizni yaxshilashga yordam beradi.",
        "ru": "Большое спасибо за отзыв! 💙 Это помогает нам становиться лучше.",
    },
    "sla_apology": {
        "uz": "⏳ Kechirasiz, hozir barcha operatorlarimiz band. Tez orada albatta ulanamiz! Ungacha savolingizni yozib qoldiring.",
        "ru": "⏳ Извините, сейчас все операторы заняты. Мы обязательно скоро подключимся! Пока можете написать свой вопрос.",
    },
    "trial_ok": {
        "uz": "🎁 Ajoyib! Bepul 1-darsga yozilish so'rovingiz qabul qilindi.\nMenejerimiz tez orada siz bilan bog'lanib, dars vaqtini kelishib oladi. 📞",
        "ru": "🎁 Отлично! Ваша заявка на бесплатный 1-й урок принята.\nМенеджер скоро свяжется с вами и согласует время урока. 📞",
    },
    "price_answer": {
        "uz": "💰 Bizda individual yondashuv bo'lgani uchun va maxsus chegirmalarni qo'llash maqsadida narxlarni menejerimiz sizga aniq hisoblab beradi.",
        "ru": "💰 У нас индивидуальный подход, поэтому, чтобы применить специальные скидки, менеджер точно рассчитает стоимость для вас.",
    },
    "ai_unavailable": {
        "uz": "🤖 AI-yordamchi hozir vaqtincha mavjud emas. Menyudan kerakli bo'limni tanlang yoki «👨‍💼 Operator bilan bog'lanish» tugmasini bosing.",
        "ru": "🤖 AI-помощник временно недоступен. Выберите раздел в меню или нажмите «👨‍💼 Связаться с оператором».",
    },
    "tutor_intro": {
        "uz": "🎓 <b>Tutor rejimi</b> yoqildi!\n\nMen — koreys tili bo'yicha shaxsiy yordamchingizman:\n• grammatika va lug'at savollari\n• uyga vazifani tekshirish (matn, rasm yoki ovozli xabar yuboring)\n• talaffuz va gap tuzish\n• 📝 mini-testlar\n\nSavolingizni yozing! 한국어 공부 화이팅! 💪",
        "ru": "🎓 <b>Режим тьютора</b> включён!\n\nЯ — ваш личный помощник по корейскому языку:\n• вопросы по грамматике и лексике\n• проверка домашнего задания (текст, фото или голосовое)\n• произношение и построение предложений\n• 📝 мини-тесты\n\nЗадайте вопрос! 한국어 공부 화이팅! 💪",
    },
    "tutor_limit": {
        "uz": "📚 Bugungi bepul tutor savollaringiz limiti ({limit} ta) tugadi.\nATKO o'quvchilari tutor'dan cheksiz foydalanadi! Kursga yozilish uchun «👨‍💼 Operator bilan bog'lanish» yoki «🎁 Bepul 1-dars» tugmasini bosing.",
        "ru": "📚 Лимит бесплатных вопросов тьютору на сегодня ({limit}) исчерпан.\nСтуденты ATKO пользуются тьютором без ограничений! Чтобы записаться, нажмите «👨‍💼 Связаться с оператором» или «🎁 Бесплатный 1-й урок».",
    },
    "materials_empty": {
        "uz": "📄 Hozircha bepul materiallar yuklanmagan. Tez orada qo'shiladi!",
        "ru": "📄 Бесплатные материалы пока не загружены. Скоро добавим!",
    },
    # --- tahrirlanmaydigan (tizim) matnlar
    "choose_lang": {"uz": "Tilni tanlang / Выберите язык:", "ru": "Tilni tanlang / Выберите язык:"},
    "phone_saved": {"uz": "✅ Raqamingiz saqlandi: {phone}", "ru": "✅ Ваш номер сохранён: {phone}"},
    "phone_needed": {
        "uz": "📱 Buning uchun avval telefon raqamingizni ulashing — pastdagi <b>«📱 Kontaktni ulashish»</b> tugmasini bosing.",
        "ru": "📱 Для этого сначала поделитесь номером телефона — нажмите кнопку <b>«📱 Поделиться контактом»</b> ниже.",
    },
    "phone_own_only": {
        "uz": "Iltimos, o'zingizning kontaktingizni «📱 Kontaktni ulashish» tugmasi orqali yuboring.",
        "ru": "Пожалуйста, отправьте свой контакт через кнопку «📱 Поделиться контактом».",
    },
    "menu": {"uz": "🏠 Asosiy menyu", "ru": "🏠 Главное меню"},
    "courses_title": {"uz": "📚 <b>Kurslar va tariflar</b>\nBatafsil ma'lumot uchun tarifni tanlang:", "ru": "📚 <b>Курсы и тарифы</b>\nВыберите тариф для подробностей:"},
    "faq_title": {"uz": "❓ <b>Ko'p so'raladigan savollar</b>", "ru": "❓ <b>Часто задаваемые вопросы</b>"},
    "faq_empty": {"uz": "Hozircha savollar ro'yxati bo'sh. Savolingizni shunchaki yozing! 😊", "ru": "Список вопросов пока пуст. Просто напишите свой вопрос! 😊"},
    "materials_title": {"uz": "📄 <b>Bepul materiallar</b>\nYuklab olish uchun tanlang:", "ru": "📄 <b>Бесплатные материалы</b>\nВыберите для скачивания:"},
    "info_title": {"uz": "ℹ️ <b>Markaz haqida</b>", "ru": "ℹ️ <b>О центре</b>"},
    "already_waiting": {"uz": "⏳ So'rovingiz allaqachon navbatda. Operator tez orada ulanadi!", "ru": "⏳ Ваш запрос уже в очереди. Оператор скоро подключится!"},
    "already_active": {"uz": "💬 Siz hozir operator <b>{operator}</b> bilan suhbatdasiz. Savolingizni yozing.", "ru": "💬 Вы сейчас общаетесь с оператором <b>{operator}</b>. Напишите ваш вопрос."},
    "file_too_big": {"uz": "⚠️ Fayl juda katta. Ruxsat etilgan hajm: {mb} MB.", "ru": "⚠️ Файл слишком большой. Допустимый размер: {mb} МБ."},
    "unsupported": {"uz": "Bu turdagi xabarni qabul qila olmayman. Matn, rasm yoki ovozli xabar yuboring.", "ru": "Я не могу принять такой тип сообщения. Отправьте текст, фото или голосовое."},
    "consultant_on": {"uz": "📚 Konsultant rejimiga qaytdingiz. Kurslar haqida istalgan savolni bering!", "ru": "📚 Вы вернулись в режим консультанта. Задавайте любые вопросы о курсах!"},
    "tutor_disabled": {"uz": "🎓 Tutor rejimi hozircha o'chirilgan.", "ru": "🎓 Режим тьютора временно отключён."},
    "quiz_choose_level": {"uz": "📝 Mini-test darajasini tanlang:", "ru": "📝 Выберите уровень мини-теста:"},
    "quiz_wait": {"uz": "⏳ Savol tayyorlanmoqda...", "ru": "⏳ Готовлю вопрос..."},
    "quiz_correct": {"uz": "✅ To'g'ri! Barakalla! 🎉", "ru": "✅ Правильно! Молодец! 🎉"},
    "quiz_wrong": {"uz": "❌ Noto'g'ri. To'g'ri javob: <b>{answer}</b>", "ru": "❌ Неверно. Правильный ответ: <b>{answer}</b>"},
    "quiz_next": {"uz": "➡️ Keyingi savol", "ru": "➡️ Следующий вопрос"},
    "quiz_stop": {"uz": "⏹ Tugatish", "ru": "⏹ Завершить"},
    "quiz_result": {"uz": "📊 Natija: {ok} / {total}", "ru": "📊 Результат: {ok} / {total}"},
    "thinking": {"uz": "✍️ ...", "ru": "✍️ ..."},
    "lang_changed": {"uz": "✅ Til o'zgartirildi.", "ru": "✅ Язык изменён."},
    "escalated": {"uz": "👨‍💼 Savolingizni operatorimizga yo'naltiraman.", "ru": "👨‍💼 Передаю ваш вопрос оператору."},
    "skip": {"uz": "⏭ O'tkazib yuborish", "ru": "⏭ Пропустить"},
    "later": {"uz": "⏭ Keyinroq", "ru": "⏭ Позже"},
    "back": {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад"},
    "trial_btn_inline": {"uz": "🎁 Bepul 1-darsga yozilish", "ru": "🎁 Записаться на бесплатный урок"},
    "operator_btn_inline": {"uz": "👨‍💼 Operator bilan bog'lanish", "ru": "👨‍💼 Связаться с оператором"},
    # --- menyu tugmalari
    "btn_courses": {"uz": "📚 Kurslar va tariflar", "ru": "📚 Курсы и тарифы"},
    "btn_trial": {"uz": "🎁 Bepul 1-dars", "ru": "🎁 Бесплатный 1-й урок"},
    "btn_materials": {"uz": "📄 Bepul materiallar", "ru": "📄 Бесплатные материалы"},
    "btn_faq": {"uz": "❓ Ko'p so'raladigan savollar", "ru": "❓ Частые вопросы"},
    "btn_tutor": {"uz": "🎓 Tutor (koreys tili yordamchisi)", "ru": "🎓 Тьютор (помощник по корейскому)"},
    "btn_operator": {"uz": "👨‍💼 Operator bilan bog'lanish", "ru": "👨‍💼 Связаться с оператором"},
    "btn_info": {"uz": "ℹ️ Markaz haqida", "ru": "ℹ️ О центре"},
    "btn_lang": {"uz": "🌐 Til / Язык", "ru": "🌐 Til / Язык"},
    "btn_contact": {"uz": "📱 Kontaktni ulashish", "ru": "📱 Поделиться контактом"},
    "btn_quiz": {"uz": "📝 Mini-test", "ru": "📝 Мини-тест"},
    "btn_consultant": {"uz": "🔙 Konsultant rejimi", "ru": "🔙 Режим консультанта"},
}

EDITABLE: dict[str, str] = {
    "welcome": "Salomlashish (/start)",
    "ask_name": "Ism so'rash",
    "ask_phone": "Telefon so'rash ({name})",
    "ask_goal": "Maqsad so'rash",
    "ask_format": "Format so'rash",
    "onboarding_done": "Ro'yxatdan o'tish yakuni",
    "operator_wait": "Operator so'rovi (ish vaqtida)",
    "operator_off_hours": "Operator so'rovi (ish vaqtidan tashqari) ({hours}, {next_open})",
    "operator_connected": "Operator ulandi ({operator})",
    "chat_closed": "Chat yopildi ({operator})",
    "rating_ask": "Baho so'rash",
    "rating_comment_ask": "Baho izohini so'rash",
    "rating_thanks": "Baho uchun rahmat",
    "sla_apology": "Operatorlar band (kechikish)",
    "trial_ok": "Bepul darsga yozildi",
    "price_answer": "Narx haqida javob",
    "ai_unavailable": "AI mavjud emas",
    "tutor_intro": "Tutor rejimi kirish matni",
    "tutor_limit": "Tutor kunlik limit tugadi ({limit})",
    "materials_empty": "Materiallar yo'q",
}


def t(key: str, lang: str = "uz", **kw: Any) -> str:
    lang = lang if lang in ("uz", "ru") else "uz"
    overrides = (st._cache or {}).get("texts") or {}
    val = None
    if key in overrides and isinstance(overrides[key], dict):
        val = overrides[key].get(lang) or None
    if not val:
        val = TEXTS.get(key, {}).get(lang) or TEXTS.get(key, {}).get("uz") or key
    if kw:
        try:
            val = val.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return val


def all_button_texts(key: str) -> set[str]:
    return {t(key, "uz"), t(key, "ru")}
