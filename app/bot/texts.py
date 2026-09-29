"""Bot matnlari (faqat o'zbek tilida; ruscha variantlar ishlatilmaydi). EDITABLE ro'yxatidagilarni admin panelda o'zgartira oladi."""
from __future__ import annotations

from typing import Any

from ..services import settings as st

TEXTS: dict[str, dict[str, str]] = {
    # ================================================================ tahrirlanadigan matnlar
    "welcome": {
        "uz": "Assalomu alaykum! 👋\n<b>ATKO Koreys Tili O'quv Markazi</b>ga xush kelibsiz!\n\nBiz koreys tili, TOPIK va EPS-TOPIK imtihonlariga tayyorlaymiz: yopiq Telegram guruhda video darslar, Zoom orqali jonli guruh darslari va individual mashg'ulotlar. 🇰🇷",
    },
    "ask_name": {
        "uz": "Tanishib olaylik 😊 Ismingiz nima?",
    },
    "ask_phone": {
        "uz": "Rahmat, {name}! 😊\n\n📱 <b>Telefon raqamingizni tasdiqlang</b>\n\nBotning barcha imkoniyatlaridan — tariflarni ko'rish va sotib olish, 🎓 AI mentor hamda menejer bilan aloqadan — foydalanish uchun telefon raqamingizni yuboring.\nMenejerlarimiz sizga kurslar haqida batafsil ma'lumot berib, sizga mos tarifni tanlashda yordam beradi.\n\n👇 Pastdagi <b>«📱 Raqamni yuborish»</b> tugmasini bosing.",
    },
    "phone_required": {
        "uz": "📱 <b>Telefon raqamingizni tasdiqlang</b>\n\nBotning barcha imkoniyatlaridan foydalanish uchun avval telefon raqamingizni yuboring.\nMenejerlarimiz sizga kurslar haqida batafsil ma'lumot berib, sizga mos tarifni tanlashda yordam beradi.\n\n👇 Pastdagi <b>«📱 Raqamni yuborish»</b> tugmasini bosing.",
    },
    "ask_goal": {
        "uz": "Koreys tilini qaysi maqsadda o'rganmoqchisiz?",
    },
    "ask_format": {
        "uz": "Qaysi ta'lim formati sizga qulay?",
    },
    "onboarding_done": {
        "uz": "Ajoyib! ✅ Endi botning barcha imkoniyatlari siz uchun ochiq.\nPastdagi menyudan kerakli bo'limni tanlang yoki savolingizni shunchaki yozing — men darhol javob beraman. 🤖",
    },
    "operator_wait": {
        "uz": "✅ So'rovingiz qabul qilindi!\n👨‍💼 Operatorimiz <b>2–10 daqiqa</b> ichida chatga ulanadi. Savolingizni hozirdan yozib qoldirishingiz mumkin.",
    },
    "operator_off_hours": {
        "uz": "🌙 Hozir ish vaqtidan tashqari (operatorlar ish vaqti: <b>{hours}</b>, yakshanba va bayram kunlari dam olish).\n\n✅ So'rovingiz navbatga qo'yildi — operator <b>{next_open}</b> dan keyin siz bilan bog'lanadi.\n🤖 Ungacha savollaringizga AI-yordamchimiz javob beradi.",
    },
    "operator_connected": {
        "uz": "👨‍💼 <b>{operator}</b> chatga ulandi va sizga yordam berishga tayyor. Savolingizni yozing!",
    },
    "chat_closed": {
        "uz": "✅ <b>Suhbat yakunlandi</b>\n\nMurojaatingiz uchun rahmat! Sizga <b>{operator}</b> yordam berdi.\nYana savollaringiz bo'lsa, shu yerga yozing yoki «👨‍💼 Operator bilan bog'lanish» tugmasini bosing — biz doim yordamga tayyormiz.\n\n🇰🇷 <i>ATKO Koreys Tili O'quv Markazi</i>",
    },
    "rating_ask": {
        "uz": "Xizmatimiz sizga yoqdimi? Iltimos, baholang:",
    },
    "rating_comment_ask": {
        "uz": "Rahmat! 🙏 Xohlasangiz, fikringizni yozib qoldiring (yoki «O'tkazib yuborish» tugmasini bosing):",
    },
    "rating_thanks": {
        "uz": "Fikringiz uchun katta rahmat! 💙 Bu bizga xizmatimizni yaxshilashga yordam beradi.",
    },
    "sla_apology": {
        "uz": "⏳ Kechirasiz, hozir barcha operatorlarimiz band. Tez orada albatta ulanamiz! Ungacha savolingizni yozib qoldiring.",
    },
    "price_by_manager": {"uz": "menejerimiz aniqlab beradi"},
    "price_note": {
        "uz": "ℹ️ Narxlar o'zgarishi mumkin.",
    },
    "enroll_request_ok": {
        "uz": "✅ So'rovingiz qabul qilindi! Menejerimiz tez orada siz bilan bog'lanib, to'lov va dars jadvali bo'yicha batafsil ma'lumot beradi.",
    },
    "ai_unavailable": {
        "uz": "🤖 AI-yordamchi hozir vaqtincha mavjud emas. Menyudan kerakli bo'limni tanlang yoki «👨‍💼 Operator bilan bog'lanish» tugmasini bosing.",
    },
    "tutor_intro": {
        "uz": "🎓 <b>AI mentor</b> — koreys tili bo'yicha shaxsiy yordamchingiz!\n\n• grammatika va lug'at savollari\n• uyga vazifani tekshirish (matn, rasm yoki ovozli xabar yuboring)\n• talaffuz va gap tuzish\n\n{limit_info}\n\nSavolingizni yozing! 한국어 공부 화이팅! 💪\n\n<i>📝 Mini-test — bosh sahifada. Qaytish uchun pastdagi «🏠 Bosh sahifa» tugmasini bosing.</i>",
    },
    "tutor_limit": {
        "uz": "📚 Bugungi bepul savollaringiz limiti ({limit} ta) tugadi.\n\n💎 <b>Premium obunachilar</b> AI mentordan cheksiz foydalanadi! Obunani pastdagi «💳 Obuna sotib olish» tugmasi orqali rasmiylashtiring.",
    },
    # ================================================================ tizim matnlari
    "phone_saved": {"uz": "✅ Raqamingiz tasdiqlandi: {phone}"},
    "phone_own_only": {
        "uz": "Iltimos, o'zingizning raqamingizni pastdagi «📱 Raqamni yuborish» tugmasi orqali yuboring.",
    },
    "menu": {"uz": "🏠 Asosiy menyu"},
    "courses_title": {"uz": "📚 <b>Tariflar va narxlar</b>\nBatafsil ma'lumot uchun tarifni tanlang:"},
    "already_waiting": {"uz": "⏳ So'rovingiz allaqachon navbatda. Operator tez orada ulanadi!"},
    "already_active": {"uz": "💬 Siz hozir <b>{operator}</b> bilan suhbatdasiz. Savolingizni yozing."},
    "file_too_big": {"uz": "⚠️ Fayl juda katta. Ruxsat etilgan hajm: {mb} MB."},
    "unsupported": {"uz": "Bu turdagi xabarni qabul qila olmayman. Matn, rasm yoki ovozli xabar yuboring."},
    "consultant_on": {"uz": "🏠 Bosh sahifadasiz. Kerakli bo'limni tanlang yoki kurslar haqida istalgan savolni yozing!"},
    "tutor_disabled": {"uz": "🎓 AI mentor hozircha o'chirilgan."},
    "tutor_unlimited": {"uz": "💎 Sizda Premium obuna bor — AI mentordan <b>cheksiz</b> foydalanasiz."},
    "tutor_daily": {"uz": "🆓 Bugun yana <b>{left} ta</b> savol berishingiz mumkin (kuniga {limit} ta). Premium obunachilar uchun — cheksiz."},
    "quiz_choose_level": {"uz": "📝 Mini-test darajasini tanlang:"},
    "quiz_wait": {"uz": "⏳ Savol tayyorlanmoqda..."},
    "quiz_correct": {"uz": "✅ To'g'ri! Barakalla! 🎉"},
    "quiz_wrong": {"uz": "❌ Noto'g'ri. To'g'ri javob: <b>{answer}</b>"},
    "quiz_next": {"uz": "➡️ Keyingi savol"},
    "quiz_stop": {"uz": "⏹ Tugatish"},
    "quiz_result": {"uz": "📊 Natija: {ok} / {total}"},
    "skip": {"uz": "⏭ O'tkazib yuborish"},
    "back": {"uz": "⬅️ Orqaga"},
    "operator_btn_inline": {"uz": "👨‍💼 Operator bilan bog'lanish"},
    "buy_btn_inline": {"uz": "💳 Sotib olish"},
    "price_label": {"uz": "💰 Narxi"},
    "packages_label": {"uz": "💰 Paketlar va narxlar"},
    "per_lesson": {"uz": "≈ {amount} / dars"},
    "best_value": {"uz": "💰 tejamkor"},
    "best_value_pct": {"uz": "💰 tejamkor, −{pct}%"},
    "choose_package": {"uz": "👇 Paketni tanlang — menejerimiz siz bilan bog'lanib, to'lov va dars jadvalini kelishib oladi."},
    "som": {"uz": "so'm"},
    "center_default": {"uz": "ℹ️ ATKO — koreys tili, TOPIK va EPS-TOPIK imtihonlariga tayyorlovchi o'quv markazi."},
    # ---------------- obuna va to'lov
    "buy_title": {
        "uz": "💎 <b>{tariff}</b>\n\n<b>Bu obuna nima?</b>\nATKO'ning yopiq Telegram guruhiga kirish huquqi. Guruhda koreys tilini noldan EPS-TOPIK va TOPIK darajasigacha mustaqil o'rganish uchun barcha video darslar va materiallar bo'limlarga ajratilgan holda joylangan:\n\n📚 <b>Guruh ichida:</b>\n• 한글 Hangul alifbosi — noldan boshlash\n• 🎬 EPS-TOPIK 960, 600, 60 va 50 — to'liq video kurslar\n• 📖 Kitoblar va qo'llanmalar\n• 🎵 Audio materiallar (tinglab tushunish)\n• ⁉️ Testlar\n• 🎞 Koreys kinolari\n• 🏆 Shogirdlarimiz natijalari\n\n<b>🎁 Obunaga qo'shimcha:</b>\n• 🎓 AI mentor — koreys tili bo'yicha savollarga 24/7 <b>cheksiz</b> javob, uyga vazifani tekshirish va mini-testlar\n• 🆕 Guruhga qo'shiladigan yangi darslar ham obuna davomida siz uchun ochiq\n\n<b>⚙️ Qanday ishlaydi?</b>\n1️⃣ Pastdan obuna muddatini tanlang\n2️⃣ <b>Payme</b> orqali xavfsiz to'lang (Uzcard / Humo)\n3️⃣ To'lovdan so'ng bot guruh havolasini darhol yuboradi\n4️⃣ «Qo'shilish so'rovi»ni yuboring — bot uni avtomatik tasdiqlaydi\n\n⏰ Obuna tugashidan 3 va 1 kun oldin eslatma keladi. Muddat tugaganda guruhga kirish yopiladi, uzaytirsangiz — darhol qayta ochiladi.\n📅 Holatini istalgan vaqtda «👤 Mening obunam» bo'limida ko'rasiz.",
    },
    "buy_unavailable": {
        "uz": "⏳ Onlayn to'lov hozircha ishlamayapti. Birozdan so'ng qayta urinib ko'ring yoki «👨‍💼 Operator bilan bog'lanish» tugmasini bosing.",
    },
    "invoice": {
        "uz": "🧾 <b>To'lov buyurtmasi №{order}</b>\n\n📦 {title}\n📅 Muddat: {days} kun\n💰 Summa: <b>{amount} so'm</b>\n\n👇 «Payme orqali to'lash» tugmasini bosing. To'lov tasdiqlangach, obunangiz avtomatik faollashadi va guruh havolasi yuboriladi.",
    },
    "pay_btn": {"uz": "💳 Payme orqali to'lash"},
    "paid_ok": {
        "uz": "🎉 <b>To'lov qabul qilindi!</b>\n\n💎 Obunangiz faollashtirildi.\n📅 Amal qilish muddati: <b>{until}</b> gacha\n\n👇 Guruhga qo'shilish uchun pastdagi tugmani bosing va «Qo'shilish so'rovi»ni yuboring — bot uni avtomatik tasdiqlaydi.",
    },
    "access_granted": {
        "uz": "💎 <b>Sizga ATKO Premium guruhiga kirish huquqi berildi!</b>\n📅 Amal qilish muddati: <b>{until}</b> gacha\n\n👇 Guruhga qo'shilish uchun pastdagi tugmani bosing va «Qo'shilish so'rovi»ni yuboring — bot uni avtomatik tasdiqlaydi.",
    },
    "join_btn": {"uz": "🔗 Guruhga qo'shilish"},
    "join_approved": {"uz": "✅ Guruhga qo'shildingiz! Darslarda omad! 한국어 화이팅! 💪"},
    "join_denied": {
        "uz": "⛔️ Guruhga kirish uchun faol Premium obuna kerak. Obunani pastdagi tugma orqali rasmiylashtiring.",
    },
    "sub_remind": {
        "uz": "⏰ <b>Obunangiz {days} kundan keyin tugaydi</b> ({until}).\n\nDarslardan uzilib qolmaslik uchun obunani oldindan uzaytiring 👇",
    },
    "sub_expired": {
        "uz": "⌛️ <b>Obunangiz muddati tugadi</b> va siz ATKO Premium guruhidan chiqarildingiz.\n\nObunani uzaytirsangiz, guruhga darhol qaytasiz 👇",
    },
    "sub_refunded": {
        "uz": "↩️ To'lovingiz bekor qilindi (pul qaytarildi). Obuna muddati shunga mos ravishda qisqartirildi.",
    },
    "renew_btn": {"uz": "🔄 Obunani uzaytirish"},
    "mysub_active": {
        "uz": "👤 <b>Mening obunam</b>\n\n💎 Tarif: <b>{tariff}</b>\n✅ Holat: <b>faol</b>\n📅 Boshlangan: {start}\n⏳ Tugaydi: <b>{until}</b>\n🗓 Qoldi: <b>{left} kun</b>\n{bar}\n\n🎓 AI mentor: <b>cheksiz</b>",
    },
    "mysub_forever": {
        "uz": "👤 <b>Mening obunam</b>\n\n💎 Tarif: <b>{tariff}</b>\n✅ Holat: <b>faol (muddatsiz)</b>\n\n🎓 AI mentor: <b>cheksiz</b>",
    },
    "mysub_expired": {
        "uz": "👤 <b>Mening obunam</b>\n\n💎 Tarif: {tariff}\n❌ Holat: <b>muddati tugagan</b> ({until})\n\n🎓 AI mentor: kuniga {limit} ta savol\n\nObunani uzaytirib, darslarni davom ettiring 👇",
    },
    "mysub_none": {
        "uz": "👤 <b>Mening obunam</b>\n\nSizda hozircha faol obuna yo'q.\n\n💎 <b>Premium obuna</b> bilan siz:\n• yopiq Telegram guruhdagi barcha video darslar (Hangul, EPS-TOPIK 960/600, kitoblar, audio, testlar)\n• 🎓 AI mentordan cheksiz foydalanish\n\nimkoniyatiga ega bo'lasiz. Hozir AI mentor: kuniga {limit} ta savol.",
    },
    "mysub_payments": {"uz": "\n\n🧾 <b>Oxirgi to'lovlar:</b>\n{items}"},
    "mysub_link_btn": {"uz": "🔗 Guruhga kirish havolasi"},
    # ---------------- namuna video, to'lov eslatmasi
    "sample_btn": {"uz": "🎬 Namuna darsni ko'rish"},
    "pay_reminder": {
        "uz": "⏳ <b>To'lov yakunlanmadi</b>\n\nSiz <b>{title}</b> uchun buyurtma yaratgan edingiz ({amount}), lekin to'lov amalga oshmadi.\n\nTo'lovni davom ettirish uchun pastdagi tugmani bosing. Muammo bo'lsa, operatorimiz yordam beradi 👇",
    },
    # ================================================================ menyu tugmalari
    "btn_courses": {"uz": "📚 Tariflar va narxlar"},
    "btn_buy": {"uz": "💳 Obuna sotib olish"},
    "btn_mysub": {"uz": "👤 Mening obunam"},
    "btn_tutor": {"uz": "🎓 AI mentor"},
    "btn_operator": {"uz": "👨‍💼 Operator bilan bog'lanish"},
    "btn_info": {"uz": "ℹ️ Markaz haqida"},
    "btn_contact": {"uz": "📱 Raqamni yuborish"},
    "btn_quiz": {"uz": "📝 Mini-test"},
    "btn_consultant": {"uz": "🏠 Bosh sahifa"},
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
    "enroll_request_ok": "Zoom / Individual paket tanlanganda (menejer bog'lanadi)",
    "choose_package": "Zoom / Individual tarif oynasida paket tanlash taklifi",
    "ai_unavailable": "AI mavjud emas",
    "tutor_intro": "AI mentor kirish matni ({limit_info})",
    "tutor_limit": "AI mentor kunlik limiti tugadi ({limit})",
    "paid_ok": "To'lov qabul qilindi ({until})",
    "access_granted": "Admin qo'lda obuna berdi ({until})",
    "sub_remind": "Obuna tugashi haqida eslatma ({days}, {until})",
    "sub_expired": "Obuna tugadi — guruhdan chiqarildi",
    "join_denied": "Obunasiz guruhga kirishga urinish",
    "pay_reminder": "To'lov yakunlanmadi — eslatma ({title}, {amount})",
}


def t(key: str, lang: str = "uz", **kw: Any) -> str:
    lang = "uz"  # bot faqat o'zbek tilida
    overrides = (st._cache or {}).get("texts") or {}
    val = None
    if key in overrides and isinstance(overrides[key], dict):
        val = overrides[key].get(lang) or None
        if val:
            from .tghtml import error as _html_error

            if _html_error(val):  # paneldan noto'g'ri HTML kiritilgan bo'lsa — standart matn ishlatiladi
                val = None
    if not val:
        val = TEXTS.get(key, {}).get(lang) or TEXTS.get(key, {}).get("uz") or key
    if kw:
        try:
            val = val.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return val


# eski versiyalardagi tugma matnlari (foydalanuvchida eski klaviatura qolgan bo'lsa ham ishlaydi)
LEGACY_BUTTONS: dict[str, set[str]] = {"btn_consultant": {"🏠 Asosiy menyu"}}


def all_button_texts(key: str) -> set[str]:
    return {t(key)} | LEGACY_BUTTONS.get(key, set())


def money(amount: int | None, lang: str = "uz") -> str:
    return f"{int(amount or 0):,}".replace(",", " ") + " " + t("som", lang)
