"""Bot matnlari (o'zbek va rus). EDITABLE ro'yxatidagilarni admin panelda o'zgartira oladi."""
from __future__ import annotations

from typing import Any

from ..services import settings as st

TEXTS: dict[str, dict[str, str]] = {
    # ================================================================ tahrirlanadigan matnlar
    "welcome": {
        "uz": "Assalomu alaykum! 👋\n<b>ATKO Koreys Tili O'quv Markazi</b>ga xush kelibsiz!\n\nBiz koreys tili, TOPIK va EPS-TOPIK imtihonlariga tayyorlaymiz: yopiq Telegram guruhda video darslar, Zoom orqali jonli guruh darslari va individual mashg'ulotlar. 🇰🇷",
        "ru": "Здравствуйте! 👋\nДобро пожаловать в <b>учебный центр корейского языка ATKO</b>!\n\nМы готовим к корейскому языку, экзаменам TOPIK и EPS-TOPIK: видеоуроки в закрытой Telegram-группе, живые групповые занятия в Zoom и индивидуальные уроки. 🇰🇷",
    },
    "ask_name": {
        "uz": "Tanishib olaylik 😊 Ismingiz nima?",
        "ru": "Давайте познакомимся 😊 Как вас зовут?",
    },
    "ask_phone": {
        "uz": "Rahmat, {name}! 😊\n\n📱 <b>Telefon raqamingizni tasdiqlang</b>\n\nBotning barcha imkoniyatlaridan — tariflarni ko'rish va sotib olish, 🎓 AI mentor hamda menejer bilan aloqadan — foydalanish uchun telefon raqamingizni yuboring.\nMenejerlarimiz sizga kurslar haqida batafsil ma'lumot berib, sizga mos tarifni tanlashda yordam beradi.\n\n👇 Pastdagi <b>«📱 Raqamni yuborish»</b> tugmasini bosing.",
        "ru": "Спасибо, {name}! 😊\n\n📱 <b>Подтвердите номер телефона</b>\n\nЧтобы пользоваться всеми возможностями бота — смотреть и покупать тарифы, 🎓 AI-ментор и связь с менеджером — отправьте свой номер телефона.\nНаши менеджеры подробно расскажут о курсах и помогут выбрать подходящий тариф.\n\n👇 Нажмите кнопку <b>«📱 Отправить номер»</b> ниже.",
    },
    "phone_required": {
        "uz": "📱 <b>Telefon raqamingizni tasdiqlang</b>\n\nBotning barcha imkoniyatlaridan foydalanish uchun avval telefon raqamingizni yuboring.\nMenejerlarimiz sizga kurslar haqida batafsil ma'lumot berib, sizga mos tarifni tanlashda yordam beradi.\n\n👇 Pastdagi <b>«📱 Raqamni yuborish»</b> tugmasini bosing.",
        "ru": "📱 <b>Подтвердите номер телефона</b>\n\nЧтобы пользоваться всеми возможностями бота, сначала отправьте свой номер телефона.\nНаши менеджеры подробно расскажут о курсах и помогут выбрать подходящий тариф.\n\n👇 Нажмите кнопку <b>«📱 Отправить номер»</b> ниже.",
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
        "uz": "Ajoyib! ✅ Endi botning barcha imkoniyatlari siz uchun ochiq.\nPastdagi menyudan kerakli bo'limni tanlang yoki savolingizni shunchaki yozing — men darhol javob beraman. 🤖",
        "ru": "Отлично! ✅ Теперь все возможности бота открыты для вас.\nВыберите раздел в меню ниже или просто напишите свой вопрос — я сразу отвечу. 🤖",
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
        "uz": "👨‍💼 <b>{operator}</b> chatga ulandi va sizga yordam berishga tayyor. Savolingizni yozing!",
        "ru": "👨‍💼 <b>{operator}</b> подключился к чату и готов помочь. Задайте свой вопрос!",
    },
    "chat_closed": {
        "uz": "✅ <b>Suhbat yakunlandi</b>\n\nMurojaatingiz uchun rahmat! Sizga <b>{operator}</b> yordam berdi.\nYana savollaringiz bo'lsa, shu yerga yozing yoki «👨‍💼 Operator bilan bog'lanish» tugmasini bosing — biz doim yordamga tayyormiz.\n\n🇰🇷 <i>ATKO Koreys Tili O'quv Markazi</i>",
        "ru": "✅ <b>Диалог завершён</b>\n\nСпасибо за обращение! Вам помогал(а) <b>{operator}</b>.\nЕсли появятся вопросы, пишите сюда или нажмите «👨‍💼 Связаться с оператором» — мы всегда готовы помочь.\n\n🇰🇷 <i>Учебный центр корейского языка ATKO</i>",
    },
    "rating_ask": {
        "uz": "Xizmatimiz sizga yoqdimi? Iltimos, baholang:",
        "ru": "Вам понравилось наше обслуживание? Пожалуйста, оцените:",
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
    "price_note": {
        "uz": "ℹ️ Narxlar o'zgarishi mumkin. Aniq narx va amaldagi chegirmalarni admin bilan aniqlashtirib olishingizni tavsiya qilamiz.",
        "ru": "ℹ️ Цены могут меняться. Рекомендуем уточнить точную стоимость и действующие скидки у администратора.",
    },
    "enroll_request_ok": {
        "uz": "✅ So'rovingiz qabul qilindi! Admin tez orada siz bilan bog'lanib, to'lov va dars jadvali bo'yicha batafsil ma'lumot beradi.",
        "ru": "✅ Ваш запрос принят! Администратор скоро свяжется с вами и расскажет об оплате и расписании занятий.",
    },
    "ai_unavailable": {
        "uz": "🤖 AI-yordamchi hozir vaqtincha mavjud emas. Menyudan kerakli bo'limni tanlang yoki «👨‍💼 Operator bilan bog'lanish» tugmasini bosing.",
        "ru": "🤖 AI-помощник временно недоступен. Выберите раздел в меню или нажмите «👨‍💼 Связаться с оператором».",
    },
    "tutor_intro": {
        "uz": "🎓 <b>AI mentor</b> — koreys tili bo'yicha shaxsiy yordamchingiz!\n\n• grammatika va lug'at savollari\n• uyga vazifani tekshirish (matn, rasm yoki ovozli xabar yuboring)\n• talaffuz va gap tuzish\n• 📝 mini-testlar\n\n{limit_info}\n\nSavolingizni yozing! 한국어 공부 화이팅! 💪",
        "ru": "🎓 <b>AI-ментор</b> — ваш личный помощник по корейскому языку!\n\n• вопросы по грамматике и лексике\n• проверка домашнего задания (текст, фото или голосовое)\n• произношение и построение предложений\n• 📝 мини-тесты\n\n{limit_info}\n\nЗадайте вопрос! 한국어 공부 화이팅! 💪",
    },
    "tutor_limit": {
        "uz": "📚 Bugungi bepul savollaringiz limiti ({limit} ta) tugadi.\n\n💎 <b>Premium obunachilar</b> AI mentordan cheksiz foydalanadi! Obunani pastdagi «💳 Obuna sotib olish» tugmasi orqali rasmiylashtiring.",
        "ru": "📚 Лимит бесплатных вопросов на сегодня ({limit}) исчерпан.\n\n💎 <b>Premium-подписчики</b> пользуются AI-ментором без ограничений! Оформите подписку кнопкой «💳 Купить подписку» ниже.",
    },
    # ================================================================ tizim matnlari
    "choose_lang": {"uz": "Tilni tanlang / Выберите язык:", "ru": "Tilni tanlang / Выберите язык:"},
    "phone_saved": {"uz": "✅ Raqamingiz tasdiqlandi: {phone}", "ru": "✅ Ваш номер подтверждён: {phone}"},
    "phone_own_only": {
        "uz": "Iltimos, o'zingizning raqamingizni pastdagi «📱 Raqamni yuborish» tugmasi orqali yuboring.",
        "ru": "Пожалуйста, отправьте свой номер через кнопку «📱 Отправить номер» ниже.",
    },
    "menu": {"uz": "🏠 Asosiy menyu", "ru": "🏠 Главное меню"},
    "courses_title": {"uz": "📚 <b>Tariflar va narxlar</b>\nBatafsil ma'lumot uchun tarifni tanlang:", "ru": "📚 <b>Тарифы и цены</b>\nВыберите тариф для подробностей:"},
    "info_title": {"uz": "ℹ️ <b>Markaz haqida</b>", "ru": "ℹ️ <b>О центре</b>"},
    "already_waiting": {"uz": "⏳ So'rovingiz allaqachon navbatda. Operator tez orada ulanadi!", "ru": "⏳ Ваш запрос уже в очереди. Оператор скоро подключится!"},
    "already_active": {"uz": "💬 Siz hozir <b>{operator}</b> bilan suhbatdasiz. Savolingizni yozing.", "ru": "💬 Вы сейчас общаетесь с <b>{operator}</b>. Напишите ваш вопрос."},
    "file_too_big": {"uz": "⚠️ Fayl juda katta. Ruxsat etilgan hajm: {mb} MB.", "ru": "⚠️ Файл слишком большой. Допустимый размер: {mb} МБ."},
    "unsupported": {"uz": "Bu turdagi xabarni qabul qila olmayman. Matn, rasm yoki ovozli xabar yuboring.", "ru": "Я не могу принять такой тип сообщения. Отправьте текст, фото или голосовое."},
    "consultant_on": {"uz": "🏠 Asosiy menyuga qaytdingiz. Kurslar haqida istalgan savolni bering!", "ru": "🏠 Вы вернулись в главное меню. Задавайте любые вопросы о курсах!"},
    "tutor_disabled": {"uz": "🎓 AI mentor hozircha o'chirilgan.", "ru": "🎓 AI-ментор временно отключён."},
    "tutor_unlimited": {"uz": "💎 Sizda Premium obuna bor — AI mentordan <b>cheksiz</b> foydalanasiz.", "ru": "💎 У вас Premium-подписка — AI-ментор доступен <b>без ограничений</b>."},
    "tutor_daily": {"uz": "🆓 Bugun yana <b>{left} ta</b> savol berishingiz mumkin (kuniga {limit} ta). Premium obunachilar uchun — cheksiz.", "ru": "🆓 Сегодня можно задать ещё <b>{left}</b> вопрос(а) (в день {limit}). Для Premium-подписчиков — без ограничений."},
    "quiz_choose_level": {"uz": "📝 Mini-test darajasini tanlang:", "ru": "📝 Выберите уровень мини-теста:"},
    "quiz_wait": {"uz": "⏳ Savol tayyorlanmoqda...", "ru": "⏳ Готовлю вопрос..."},
    "quiz_correct": {"uz": "✅ To'g'ri! Barakalla! 🎉", "ru": "✅ Правильно! Молодец! 🎉"},
    "quiz_wrong": {"uz": "❌ Noto'g'ri. To'g'ri javob: <b>{answer}</b>", "ru": "❌ Неверно. Правильный ответ: <b>{answer}</b>"},
    "quiz_next": {"uz": "➡️ Keyingi savol", "ru": "➡️ Следующий вопрос"},
    "quiz_stop": {"uz": "⏹ Tugatish", "ru": "⏹ Завершить"},
    "quiz_result": {"uz": "📊 Natija: {ok} / {total}", "ru": "📊 Результат: {ok} / {total}"},
    "lang_changed": {"uz": "✅ Til o'zgartirildi.", "ru": "✅ Язык изменён."},
    "skip": {"uz": "⏭ O'tkazib yuborish", "ru": "⏭ Пропустить"},
    "back": {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад"},
    "operator_btn_inline": {"uz": "👨‍💼 Operator bilan bog'lanish", "ru": "👨‍💼 Связаться с оператором"},
    "admin_btn_inline": {"uz": "👨‍💼 Admin bilan bog'lanish", "ru": "👨‍💼 Связаться с администратором"},
    "buy_btn_inline": {"uz": "💳 Sotib olish", "ru": "💳 Купить"},
    "price_label": {"uz": "💰 Narxi", "ru": "💰 Стоимость"},
    "price_ask_admin": {"uz": "Narxni admin bilan aniqlashtiring", "ru": "Уточните стоимость у администратора"},
    "som": {"uz": "so'm", "ru": "сум"},
    # ---------------- obuna va to'lov
    "buy_title": {
        "uz": "💎 <b>{tariff}</b>\n\n<b>Bu obuna nima?</b>\nATKO'ning yopiq Telegram guruhiga kirish huquqi. Guruhda koreys tilini noldan EPS-TOPIK va TOPIK darajasigacha mustaqil o'rganish uchun barcha video darslar va materiallar bo'limlarga ajratilgan holda joylangan:\n\n📚 <b>Guruh ichida:</b>\n• 한글 Hangul alifbosi — noldan boshlash\n• 🎬 EPS-TOPIK 960, 600, 60 va 50 — to'liq video kurslar\n• 📖 Kitoblar va qo'llanmalar\n• 🎵 Audio materiallar (tinglab tushunish)\n• ⁉️ Testlar\n• 🎞 Koreys kinolari\n• 🏆 Shogirdlarimiz natijalari\n\n<b>🎁 Obunaga qo'shimcha:</b>\n• 🎓 AI mentor — koreys tili bo'yicha savollarga 24/7 <b>cheksiz</b> javob, uyga vazifani tekshirish va mini-testlar\n• 🆕 Guruhga qo'shiladigan yangi darslar ham obuna davomida siz uchun ochiq\n\n<b>⚙️ Qanday ishlaydi?</b>\n1️⃣ Pastdan obuna muddatini tanlang\n2️⃣ <b>Payme</b> orqali xavfsiz to'lang (Uzcard / Humo)\n3️⃣ To'lovdan so'ng bot guruh havolasini darhol yuboradi\n4️⃣ «Qo'shilish so'rovi»ni yuboring — bot uni avtomatik tasdiqlaydi\n\n⏰ Obuna tugashidan 3 va 1 kun oldin eslatma keladi. Muddat tugaganda guruhga kirish yopiladi, uzaytirsangiz — darhol qayta ochiladi.\n📅 Holatini istalgan vaqtda «👤 Mening obunam» bo'limida ko'rasiz.",
        "ru": "💎 <b>{tariff}</b>\n\n<b>Что это за подписка?</b>\nДоступ в закрытую Telegram-группу ATKO. В группе по разделам собраны все видеоуроки и материалы для самостоятельного изучения корейского — с нуля до уровня EPS-TOPIK и TOPIK:\n\n📚 <b>Внутри группы:</b>\n• 한글 Алфавит хангыль — старт с нуля\n• 🎬 EPS-TOPIK 960, 600, 60 и 50 — полные видеокурсы\n• 📖 Книги и пособия\n• 🎵 Аудиоматериалы (аудирование)\n• ⁉️ Тесты\n• 🎞 Корейские фильмы\n• 🏆 Результаты наших учеников\n\n<b>🎁 Дополнительно к подписке:</b>\n• 🎓 AI-ментор — ответы на вопросы по корейскому 24/7 <b>без ограничений</b>, проверка домашних заданий и мини-тесты\n• 🆕 Новые уроки, добавляемые в группу, тоже доступны вам в течение подписки\n\n<b>⚙️ Как это работает?</b>\n1️⃣ Выберите срок подписки ниже\n2️⃣ Безопасно оплатите через <b>Payme</b> (Uzcard / Humo)\n3️⃣ После оплаты бот сразу пришлёт ссылку на группу\n4️⃣ Отправьте «заявку на вступление» — бот одобрит её автоматически\n\n⏰ За 3 и 1 день до окончания придёт напоминание. По окончании срока доступ закрывается, после продления — сразу открывается снова.\n📅 Статус подписки всегда можно посмотреть в разделе «👤 Моя подписка».",
    },
    "buy_unavailable": {
        "uz": "⏳ Onlayn to'lov hozircha sozlanmagan. Obunani rasmiylashtirish uchun admin bilan bog'laning.",
        "ru": "⏳ Онлайн-оплата пока не настроена. Для оформления подписки свяжитесь с администратором.",
    },
    "invoice": {
        "uz": "🧾 <b>To'lov buyurtmasi №{order}</b>\n\n📦 {title}\n📅 Muddat: {days} kun\n💰 Summa: <b>{amount} so'm</b>\n\n👇 «Payme orqali to'lash» tugmasini bosing. To'lov tasdiqlangach, obunangiz avtomatik faollashadi va guruh havolasi yuboriladi.",
        "ru": "🧾 <b>Заказ на оплату №{order}</b>\n\n📦 {title}\n📅 Срок: {days} дн.\n💰 Сумма: <b>{amount} сум</b>\n\n👇 Нажмите «Оплатить через Payme». После подтверждения оплаты подписка активируется автоматически и придёт ссылка на группу.",
    },
    "pay_btn": {"uz": "💳 Payme orqali to'lash", "ru": "💳 Оплатить через Payme"},
    "paid_ok": {
        "uz": "🎉 <b>To'lov qabul qilindi!</b>\n\n💎 Obunangiz faollashtirildi.\n📅 Amal qilish muddati: <b>{until}</b> gacha\n\n👇 Guruhga qo'shilish uchun pastdagi tugmani bosing va «Qo'shilish so'rovi»ni yuboring — bot uni avtomatik tasdiqlaydi.",
        "ru": "🎉 <b>Оплата получена!</b>\n\n💎 Подписка активирована.\n📅 Действует до: <b>{until}</b>\n\n👇 Нажмите кнопку ниже и отправьте «Заявку на вступление» — бот одобрит её автоматически.",
    },
    "access_granted": {
        "uz": "💎 <b>Sizga ATKO Premium guruhiga kirish huquqi berildi!</b>\n📅 Amal qilish muddati: <b>{until}</b> gacha\n\n👇 Guruhga qo'shilish uchun pastdagi tugmani bosing va «Qo'shilish so'rovi»ni yuboring — bot uni avtomatik tasdiqlaydi.",
        "ru": "💎 <b>Вам открыт доступ в группу ATKO Premium!</b>\n📅 Действует до: <b>{until}</b>\n\n👇 Нажмите кнопку ниже и отправьте «Заявку на вступление» — бот одобрит её автоматически.",
    },
    "join_btn": {"uz": "🔗 Guruhga qo'shilish", "ru": "🔗 Вступить в группу"},
    "join_approved": {"uz": "✅ Guruhga qo'shildingiz! Darslarda omad! 한국어 화이팅! 💪", "ru": "✅ Вы в группе! Успехов в учёбе! 한국어 화이팅! 💪"},
    "join_denied": {
        "uz": "⛔️ Guruhga kirish uchun faol Premium obuna kerak. Obunani pastdagi tugma orqali rasmiylashtiring.",
        "ru": "⛔️ Для вступления в группу нужна активная Premium-подписка. Оформите её кнопкой ниже.",
    },
    "sub_remind": {
        "uz": "⏰ <b>Obunangiz {days} kundan keyin tugaydi</b> ({until}).\n\nDarslardan uzilib qolmaslik uchun obunani oldindan uzaytiring 👇",
        "ru": "⏰ <b>Ваша подписка закончится через {days} дн.</b> ({until}).\n\nЧтобы не прерывать обучение, продлите подписку заранее 👇",
    },
    "sub_expired": {
        "uz": "⌛️ <b>Obunangiz muddati tugadi</b> va siz ATKO Premium guruhidan chiqarildingiz.\n\nObunani uzaytirsangiz, guruhga darhol qaytasiz 👇",
        "ru": "⌛️ <b>Срок подписки истёк</b>, и вы были исключены из группы ATKO Premium.\n\nПродлите подписку — и сразу вернётесь в группу 👇",
    },
    "sub_refunded": {
        "uz": "↩️ To'lovingiz bekor qilindi (pul qaytarildi). Obuna muddati shunga mos ravishda qisqartirildi.",
        "ru": "↩️ Ваш платёж отменён (деньги возвращены). Срок подписки сокращён соответственно.",
    },
    "renew_btn": {"uz": "🔄 Obunani uzaytirish", "ru": "🔄 Продлить подписку"},
    "mysub_active": {
        "uz": "👤 <b>Mening obunam</b>\n\n💎 Tarif: <b>{tariff}</b>\n✅ Holat: <b>faol</b>\n📅 Boshlangan: {start}\n⏳ Tugaydi: <b>{until}</b>\n🗓 Qoldi: <b>{left} kun</b>\n{bar}\n\n🎓 AI mentor: <b>cheksiz</b>",
        "ru": "👤 <b>Моя подписка</b>\n\n💎 Тариф: <b>{tariff}</b>\n✅ Статус: <b>активна</b>\n📅 Начало: {start}\n⏳ Окончание: <b>{until}</b>\n🗓 Осталось: <b>{left} дн.</b>\n{bar}\n\n🎓 AI-ментор: <b>без ограничений</b>",
    },
    "mysub_forever": {
        "uz": "👤 <b>Mening obunam</b>\n\n💎 Tarif: <b>{tariff}</b>\n✅ Holat: <b>faol (muddatsiz)</b>\n\n🎓 AI mentor: <b>cheksiz</b>",
        "ru": "👤 <b>Моя подписка</b>\n\n💎 Тариф: <b>{tariff}</b>\n✅ Статус: <b>активна (бессрочно)</b>\n\n🎓 AI-ментор: <b>без ограничений</b>",
    },
    "mysub_expired": {
        "uz": "👤 <b>Mening obunam</b>\n\n💎 Tarif: {tariff}\n❌ Holat: <b>muddati tugagan</b> ({until})\n\n🎓 AI mentor: kuniga {limit} ta savol\n\nObunani uzaytirib, darslarni davom ettiring 👇",
        "ru": "👤 <b>Моя подписка</b>\n\n💎 Тариф: {tariff}\n❌ Статус: <b>истекла</b> ({until})\n\n🎓 AI-ментор: {limit} вопроса в день\n\nПродлите подписку и продолжайте обучение 👇",
    },
    "mysub_none": {
        "uz": "👤 <b>Mening obunam</b>\n\nSizda hozircha faol obuna yo'q.\n\n💎 <b>Premium obuna</b> bilan siz:\n• yopiq Telegram guruhdagi barcha video darslar (Hangul, EPS-TOPIK 960/600, kitoblar, audio, testlar)\n• 🎓 AI mentordan cheksiz foydalanish\n\nimkoniyatiga ega bo'lasiz. Hozir AI mentor: kuniga {limit} ta savol.",
        "ru": "👤 <b>Моя подписка</b>\n\nУ вас пока нет активной подписки.\n\n💎 С <b>Premium-подпиской</b> вы получаете:\n• все видеоуроки в закрытой Telegram-группе (Хангыль, EPS-TOPIK 960/600, книги, аудио, тесты)\n• 🎓 AI-ментор без ограничений\n\nСейчас AI-ментор: {limit} вопроса в день.",
    },
    "mysub_payments": {"uz": "\n\n🧾 <b>Oxirgi to'lovlar:</b>\n{items}", "ru": "\n\n🧾 <b>Последние платежи:</b>\n{items}"},
    "mysub_link_btn": {"uz": "🔗 Guruhga kirish havolasi", "ru": "🔗 Ссылка на группу"},
    # ---------------- promokod, namuna video, to'lov eslatmasi
    "promo_btn": {"uz": "🎟 Promokod kiritish", "ru": "🎟 Ввести промокод"},
    "promo_remove_btn": {"uz": "✖️ Promokodni bekor qilish", "ru": "✖️ Отменить промокод"},
    "promo_ask": {"uz": "🎟 Promokodni yozib yuboring:", "ru": "🎟 Отправьте промокод:"},
    "promo_ok": {"uz": "✅ Promokod <b>{code}</b> qo'llandi: <b>−{percent}%</b> chegirma!\nEndi obuna muddatini tanlang 👇", "ru": "✅ Промокод <b>{code}</b> применён: скидка <b>−{percent}%</b>!\nТеперь выберите срок подписки 👇"},
    "promo_applied_line": {"uz": "🎟 Qo'llangan promokod: <b>{code}</b> (−{percent}%)", "ru": "🎟 Применён промокод: <b>{code}</b> (−{percent}%)"},
    "promo_not_found": {"uz": "❌ Bunday promokod topilmadi. Tekshirib, qayta yozing.", "ru": "❌ Такой промокод не найден. Проверьте и введите снова."},
    "promo_inactive": {"uz": "❌ Bu promokod faol emas.", "ru": "❌ Этот промокод не активен."},
    "promo_expired": {"uz": "⌛️ Bu promokodning muddati tugagan.", "ru": "⌛️ Срок действия промокода истёк."},
    "promo_exhausted": {"uz": "😔 Afsuski, bu promokod limiti tugagan.", "ru": "😔 К сожалению, лимит этого промокода исчерпан."},
    "promo_used_by_you": {"uz": "ℹ️ Siz bu promokoddan allaqachon foydalangansiz.", "ru": "ℹ️ Вы уже использовали этот промокод."},
    "promo_wrong_plan": {"uz": "ℹ️ Bu promokod boshqa obuna muddati uchun amal qiladi.", "ru": "ℹ️ Этот промокод действует для другого срока подписки."},
    "promo_removed": {"uz": "Promokod bekor qilindi.", "ru": "Промокод отменён."},
    "free_ok": {
        "uz": "🎉 <b>Tabriklaymiz!</b> Promokod bilan obuna <b>bepul</b> faollashtirildi.\n📅 Amal qilish muddati: <b>{until}</b> gacha\n\n👇 Guruhga qo'shilish uchun pastdagi tugmani bosing va «Qo'shilish so'rovi»ni yuboring.",
        "ru": "🎉 <b>Поздравляем!</b> Подписка по промокоду активирована <b>бесплатно</b>.\n📅 Действует до: <b>{until}</b>\n\n👇 Нажмите кнопку ниже и отправьте «Заявку на вступление».",
    },
    "sample_btn": {"uz": "🎬 Namuna darsni ko'rish", "ru": "🎬 Посмотреть пример урока"},
    "pay_reminder": {
        "uz": "⏳ <b>To'lov yakunlanmadi</b>\n\nSiz <b>{title}</b> uchun buyurtma yaratgan edingiz ({amount}), lekin to'lov amalga oshmadi.\n\nTo'lovni davom ettirish uchun pastdagi tugmani bosing. Muammo bo'lsa, operatorimiz yordam beradi 👇",
        "ru": "⏳ <b>Оплата не завершена</b>\n\nВы создали заказ на <b>{title}</b> ({amount}), но оплата не прошла.\n\nЧтобы продолжить, нажмите кнопку ниже. Если возникли трудности — оператор поможет 👇",
    },
    # ================================================================ menyu tugmalari
    "btn_courses": {"uz": "📚 Tariflar va narxlar", "ru": "📚 Тарифы и цены"},
    "btn_buy": {"uz": "💳 Obuna sotib olish", "ru": "💳 Купить подписку"},
    "btn_mysub": {"uz": "👤 Mening obunam", "ru": "👤 Моя подписка"},
    "btn_tutor": {"uz": "🎓 AI mentor", "ru": "🎓 AI-ментор"},
    "btn_operator": {"uz": "👨‍💼 Operator bilan bog'lanish", "ru": "👨‍💼 Связаться с оператором"},
    "btn_info": {"uz": "ℹ️ Markaz haqida", "ru": "ℹ️ О центре"},
    "btn_lang": {"uz": "🌐 Til / Язык", "ru": "🌐 Til / Язык"},
    "btn_contact": {"uz": "📱 Raqamni yuborish", "ru": "📱 Отправить номер"},
    "btn_quiz": {"uz": "📝 Mini-test", "ru": "📝 Мини-тест"},
    "btn_consultant": {"uz": "🏠 Asosiy menyu", "ru": "🏠 Главное меню"},
}

EDITABLE: dict[str, str] = {
    "welcome": "Salomlashish (/start)",
    "ask_name": "Ism so'rash",
    "ask_phone": "Telefon so'rash — ro'yxatdan o'tishda ({name})",
    "phone_required": "Telefon so'rash — raqam yubormay bo'limga kirmoqchi bo'lganda",
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
    "price_note": "Narxlar ostidagi eslatma",
    "buy_title": "Obuna haqida batafsil — sotib olish oynasi ({tariff})",
    "enroll_request_ok": "2–4-tarifga yozilish so'rovi qabul qilindi",
    "ai_unavailable": "AI mavjud emas",
    "tutor_intro": "AI mentor kirish matni ({limit_info})",
    "tutor_limit": "AI mentor kunlik limiti tugadi ({limit})",
    "paid_ok": "To'lov qabul qilindi ({until})",
    "access_granted": "Admin qo'lda obuna berdi ({until})",
    "sub_remind": "Obuna tugashi haqida eslatma ({days}, {until})",
    "sub_expired": "Obuna tugadi — guruhdan chiqarildi",
    "join_denied": "Obunasiz guruhga kirishga urinish",
    "pay_reminder": "To'lov yakunlanmadi — eslatma ({title}, {amount})",
    "free_ok": "100% promokod bilan bepul faollashtirildi ({until})",
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


def money(amount: int | None, lang: str = "uz") -> str:
    return f"{int(amount or 0):,}".replace(",", " ") + " " + t("som", lang)
