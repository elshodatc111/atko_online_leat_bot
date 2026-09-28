# ATKO Lead platforma v2 — Telegram bot + Payme + yopiq guruh + operator/admin paneli

ATKO Koreys Tili O'quv Markazi uchun **Telegram bot** va operatorlar ishlaydigan **veb-panel**. Bot va panel bitta dasturda ishlaydi.

- **Bot:** o'zbek va rus tillarida, OpenAI bilan ishlaydi.
- **To'lov:** Payme orqali qabul qilinadi.
- **Yopiq Premium guruh:** a'zolikni tizim o'zi boshqaradi.

**Texnologiyalar:**
- Python **3.14** (3.14.7 da sinovdan o'tgan);
- aiogram 3 (bot);
- FastAPI + Jinja2 + HTMX (panel);
- SQLite (ma'lumotlar bazasi);
- OpenAI (AI);
- Payme Merchant API (to'lov).

---

## 1. Imkoniyatlar

### Telegram bot
| Bo'lim | Tavsif |
|---|---|
| Ro'yxatdan o'tish | Til → ism → **«📱 Raqamni yuborish»** (majburiy) → maqsad → format. Raqam tasdiqlanmaguncha botning boshqa bo'limlari yopiq. Raqam faqat shu tugma orqali qabul qilinadi |
| 📚 Tariflar va narxlar | 4 ta tarif. Narxlar paneldan kiritiladi. Har bir narx ostida «aniq narxni admin bilan aniqlashtiring» eslatmasi turadi |
| 💳 Obuna sotib olish | 1-tarif (yopiq Telegram guruh, 1/3/12 oy) — **Payme** orqali. Asosiy menyuda tugma yo'q; «Tariflar», «Mening obunam» va AI mentor limiti xabarlaridan ochiladi. Oynada: batafsil ma'lumot, 🎟 promokod, 🎬 namuna dars. To'lovdan keyin guruh havolasi avtomatik keladi |
| 🎟 Promokod | Foizli chegirma (1–100%). «Birinchi N ta foydalanuvchi», muddat va obuna varianti bo'yicha cheklash mumkin. **100%** bo'lsa — Payme'siz darhol bepul faollashadi |
| ⏳ To'lov eslatmasi | To'lov oynasini ochib, to'lamay qolganlarga 60 daqiqadan keyin (sozlanadi) **bir marta** «To'lash» tugmali eslatma |
| 👤 Mening obunam | Holat, tugash sanasi, qolgan kunlar, progress, to'lovlar tarixi, «Guruh havolasi» va «Uzaytirish» tugmalari |
| 🎓 AI mentor | Koreys tili yordamchisi: grammatika, uyga vazifani tekshirish (matn, rasm, ovoz), mini-testlar. OpenAI'ga yuklangan darsliklardan foydalanadi. **Premium obunachilarga cheksiz**, qolganlarga kuniga 3 ta savol |
| 👨‍💼 Operator bilan bog'lanish | Ish vaqtida «2–10 daqiqada ulanadi», ish vaqtidan tashqari navbatga qo'yadi (ungacha AI javob beradi). 2–4-tariflar uchun «Admin bilan bog'lanish» |
| 🤖 AI-konsultant | Tariflar va narxlar haqida javob beradi, lead ma'lumotlarini to'ldiradi, kerak bo'lsa operatorga ulaydi |
| ⭐ Baho | Chat yopilgach bitta qatorda ixcham `1⭐ … 5⭐` tugmalari, keyin ixtiyoriy izoh |

**Operator javoblari** leadga shunday sarlavha bilan boradi:
```
👨‍💼 Menejer Dilnoza · ATKO
┄┄┄┄┄┄┄┄┄┄┄┄
Assalomu alaykum! ...
```

### Yopiq Premium guruh (1-tarif)
- Guruhga faqat **«qo'shilish so'rovi»** orqali kiriladi. Bot faqat obunasi faol bo'lganlarning so'rovini tasdiqlaydi, shuning uchun havola boshqaga berib yuborilsa ham to'lovsiz kirib bo'lmaydi.
- Obuna tugashidan **3 va 1 kun oldin** foydalanuvchiga «Uzaytiring» eslatmasi boradi.
- Muddati tugaganlar guruhdan **avtomatik chiqariladi**. Qayta to'lov qilsa, yana qo'shila oladi.
- Guruhga obunasiz qo'shilganlar ham avtomatik chiqariladi. Xodimlar va «muddatsiz» ruxsat berilganlar bundan mustasno.
- **Payme'da to'lov bekor qilinsa (pul qaytarilsa)**, obuna shu to'lov kunlariga qisqaradi va kerak bo'lsa foydalanuvchi guruhdan chiqariladi.

### Veb-panel
- **Kirish:** Telegram ID kiritiladi, bot shu akkauntga **6 xonali kod** yuboradi. Kod 5 daqiqa amal qiladi va 5 marta urinish mumkin.
- **💬 Chatlar:**
  - navbat, «Menga ochdim», o'tkazish, yopish;
  - matn, rasm, audio, video va fayl almashish;
  - javob shablonlari, «🤖 AI taklif» tugmasi;
  - leadning har bir harakati (yozgan xabarlari va bosgan tugmalari) chat tarixida ko'rinadi.
- **💎 Obunachilar:**
  - Telegram ID va kunlar soni bo'yicha **qo'lda obuna berish**;
  - muddatni ± uzaytirish yoki aniq sana qo'yish, muddatsiz ruxsat, bekor qilish;
  - guruh havolasini qayta yuborish, guruhni sinxronlash, hodisalar tarixi.
- **💳 To'lovlar:** Payme buyurtmalari (chegirma bo'lsa asl narx ham), kunlik va oylik tushum grafiklari, Excel.
- **🎟 Promokodlar:** yaratish, limit (birinchi N ta), muddat, variant, yoqish/o'chirish; kim ishlatgani va to'lov jarayonidagilar.
- **🎬 Namuna video:** «Tariflar va narxlar» → 1-tarif kartasi. Video bir marta Telegram bulutiga yuklanadi (`file_id`), foydalanuvchilarga serverdan emas, Telegramdan yuboriladi.
- **📚 Tariflar va narxlar:** 4 ta tarif, narx va davr, 1-tarifning 1/3/12 oylik variantlari (narxi va kunlar soni).
- **🩺 Tizim holati:**
  - tekshiriladi: bot, webhook/polling, guruh va bot huquqlari, OpenAI, vector store, Payme, baza, disk, fon vazifalari, operatorlar;
  - oxirgi xatolar ro'yxati;
  - «🛠 tuzatish» tugmalari;
  - avtomatik tuzatish: to'xtab qolgan bot va fon vazifalari qayta ishga tushiriladi;
  - biror qism ishdan chiqsa yoki tiklansa, adminga Telegramda xabar boradi.
- Leadlar, statistika, operatorlar, manba havolalari, ommaviy xabar, savollar tahlili, avto-eslatmalar, bot matnlari, Excel eksport (bot orqali Telegramga), harakatlar jurnali, sozlamalar.

---

## 2. Kompyuterda (Windows) ishga tushirish

1. **`install.bat`** — virtual muhit yaratiladi va kutubxonalar o'rnatiladi. Oxirida `.env` ochiladi.
2. `.env` ni to'ldiring: `BOT_TOKEN`, `ADMIN_TG_IDS` (sizning Telegram ID), `OPENAI_API_KEY`, `SECRET_KEY`.
3. **`start.bat`** → brauzerda **http://localhost:8000** ni oching.
4. Telegram ID ingizni kiriting. Bot sizga kod yuboradi, kodni kiritsangiz panel ochiladi.

> **Yangilash (v1 → v2):** dasturni to'xtating va yangi fayllarni eskisining ustidan ko'chiring. Ma'lumotlar bazasi o'zi yangilanadi: yangi ustunlar, 4 ta tarif va yangi eslatmalar qo'shiladi, eski leadlar va chatlar saqlanadi. `pip install -r requirements.txt` ni qayta ishga tushiring.

---

## 3. Yopiq Premium guruhni sozlash

1. Telegramda guruhni oching → **Adminlar → Admin qo'shish** → botingizni tanlang.
2. Botga ikkita huquq bering: **«Foydalanuvchilarni bloklash»** (ban) va **«Havola orqali taklif qilish»** (invite).
3. Bot adminga «Botning guruhdagi holati o'zgardi…» xabarini yuboradi.
4. Panel → **Sozlamalar → 👥 Yopiq Premium guruh** → guruhni tanlang → **Saqlash**.
5. Panel → **🩺 Tizim holati** → «Yopiq Premium guruh» qatori 🟢 bo'lishi kerak.
6. Guruhda allaqachon bor a'zolar uchun: **💎 Obunachilar → Qo'lda obuna berish**. Telegram ID va kunlar sonini kiriting. O'qituvchi va mentorlar uchun «Muddatsiz» belgisini qo'ying.
   - A'zoning ID sini bilish uchun u botga `/myid` yozadi.
   - Telegram bot foydalanuvchini guruhga to'g'ridan-to'g'ri qo'sha olmaydi. Shuning uchun bot unga shaxsiy «qo'shilish» havolasini yuboradi, buning uchun foydalanuvchi botga oldin `/start` bosgan bo'lishi kerak. Aks holda panel havolani ko'rsatadi va uni o'zingiz yuborasiz.

> Muhim: Telegram botga guruhdagi barcha a'zolar ro'yxatini bermaydi. Shuning uchun guruhda **oldindan bor** a'zolarni bot o'zi aniqlay olmaydi. Ularga «Qo'lda obuna berish» orqali obuna bering, shunda tizim ularni kuzatadi va muddati tugaganda chiqaradi. Yangi qo'shilganlar esa avtomatik tekshiriladi.

---

## 4. Payme Merchant API

### 4.1. Payme kabinetida
1. [business.payme.uz](https://business.payme.uz) → **Kassa** → Sozlamalar (Developers / Endpoint).
2. **Endpoint URL:** `https://SIZNING-MANZIL/payme`. Serverda bu `https://sayt.alwaysdata.net/payme`, ngrok bilan sinashda `https://xxxx.ngrok-free.app/payme` bo'ladi.
3. **Hisob (account) maydoni:** `order_id` (turi: raqam). Nomi boshqa bo'lsa, panelda ham shuni yozing.
4. **Merchant ID**, **test kaliti** va **asosiy kalit**ni nusxalang.

### 4.2. Panelda
**Sozlamalar → 💳 Payme:** Merchant ID, test kaliti va asosiy kalitni kiriting. Sinov paytida **🧪 Test rejimi** yoqilgan bo'lsin.

MXIK (IKPU) kodi, qadoq kodi va QQS foizi buxgalterdan olinadi. Ular kiritilgach, soliq cheki ma'lumotlari Payme'ga avtomatik yuboriladi.

**📚 Tariflar va narxlar:** 1-tarif variantlariga (1, 3, 12 oy) narx kiriting. Narxi 0 bo'lgan variant botda sotilmaydi.

### 4.3. ngrok bilan kompyuterda sinash
Payme serveri `localhost` ga ulana olmaydi, shuning uchun vaqtincha ochiq manzil kerak:

1. [ngrok.com](https://ngrok.com) da ro'yxatdan o'ting va Windows uchun ngrok'ni yuklab oling.
2. Terminalda (bir marta): `ngrok config add-authtoken SIZNING_TOKEN`
3. Dastur ishlab turganda: `ngrok http 8000`
4. ngrok ko'rsatgan manzilni nusxalang (masalan, `https://ab12-34-56.ngrok-free.app`).
5. `.env` da `PANEL_URL=https://ab12-34-56.ngrok-free.app` yozing va `start.bat` ni qayta ishga tushiring.
6. Payme **test** kassasida Endpoint URL ni `https://ab12-34-56.ngrok-free.app/payme` qiling.
7. Payme sinov muhitida ([test.paycom.uz](https://test.paycom.uz)) kassani tanlang va sinov stsenariylarini ishga tushiring. Tekshiriladigan usullar: CheckPerformTransaction, CreateTransaction, PerformTransaction, CancelTransaction, CheckTransaction, GetStatement.
8. Botda **📚 Tariflar → Premium → 💳 Sotib olish → 1 oy → Payme orqali to'lash** — test kartasi bilan to'lang: `8600 4954 7331 6478`, muddati `03/99`, SMS kod `666666`. Obuna yoqilishi va guruh havolasi kelishi kerak.
   - Payme so'rovlarini jonli ko'rish: brauzerda `http://127.0.0.1:4040` (ngrok inspektori).
   - Endpoint tekshiruvi: brauzerda `https://…ngrok-free.app/payme` ochilsa `{"detail":"Method Not Allowed"}` chiqishi — manzil ishlayapti degani.
   - Sinov muhitidagi har bir stsenariy uchun botdan **yangi buyurtma** yarating (summa tiyinda: so'm × 100).
9. **🩺 Tizim holati → Payme** qatorida «Payme so'rovi: … oldin» yozuvi ko'rinadi.

> ngrok'ning bepul manzili har safar o'zgaradi. O'zgarsa, `.env` va Payme kabinetini yangilang. Sinov tugagach, Test rejimini o'chiring va ishchi server manzilini kiriting.

---

## 5. AI mentor darsliklari (OpenAI Storage)
1. [platform.openai.com](https://platform.openai.com) → **Storage → Vector stores → Create**.
2. PDF darsliklarni shu vector store'ga yuklang.
3. Vector store ID sini (`vs_...`) nusxalang → panel → **Sozlamalar → OpenAI → «AI mentor darsliklari»** → saqlang.
4. **🩺 Tizim holati** qatorida fayllar soni ko'rinadi.

AI mentor savolga javob berishdan oldin shu darsliklardan qidiradi.

Model nomi **Sozlamalar → Asosiy model** maydonida o'zgartiriladi (masalan, `gpt-6-luna` tejamkor, `gpt-6-sol` kuchliroq). Kunlik token limitini ham shu yerda qo'ying.

---

## 6. alwaysdata.com serveriga joylash
1. **Environment → Python** versiyasini **3.14** qiling. Loyihani `~/atko` ga yuklang.
2. SSH orqali:
   ```bash
   cd ~/atko && python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt && cp .env.example .env && nano .env
   ```
3. `.env` ga quyidagilarni yozing: `BOT_MODE=webhook`, `WEBHOOK_BASE_URL=https://SAYT.alwaysdata.net`, `WEBHOOK_SECRET=uzun-matn`, `PANEL_URL=https://SAYT.alwaysdata.net`. `HOST` va `PORT` bo'sh qolsin.
4. **Web → Sites → Add a site:**
   - Type: **User program**
   - Command: `/home/LOGIN/atko/.venv/bin/python run.py`
   - Working directory: `/home/LOGIN/atko`
5. `https://SAYT.alwaysdata.net/health` → `{"ok": true}`. So'ng Payme kabinetida Endpoint URL ni `https://SAYT.alwaysdata.net/payme` ga o'zgartiring.

**Muhim:**
- Dastur bitta jarayonda ishlashi kerak, bir nechta worker yoqmang.
- Serverga o'tgach, kompyuterdagi botni to'xtating: bitta token bir vaqtda ikki joyda ishlamaydi.

---

## 7. Muammolar
| Muammo | Yechim |
|---|---|
| Kod kelmayapti | Botga `/start` yozganmisiz? `.env` dagi `ADMIN_TG_IDS` to'g'rimi? Kodni 60 soniyadan keyin qayta so'rang |
| Obunachi guruhga kira olmayapti | 🩺 Tizim holati → «Yopiq Premium guruh» 🟢 bo'lishi kerak (bot admin, huquqlar to'liq). Obunachilar → «🔗 Havolani yuborish» |
| Payme «Avtorizatsiya xatosi» | Test/ishchi rejim va kalit mos kelyaptimi? Test rejimida test kaliti ishlatiladi |
| AI javob bermayapti | 🩺 Tizim holati → «AI ni sinash». Kalit, model nomi va kunlik limitni tekshiring |

## 8. O'zgarishlar tarixi
- **v2.2:**
  - 🎬 namuna video: paneldan (50 MB gacha) yoki admin botga to'g'ridan-to'g'ri yuboradi (hajm cheklovi yo'q) → «Namuna video sifatida saqlash»; almashtirish — yangi videoni yuklash;
  - 🎟 promokodlar: 1–100%, «birinchi N ta», muddat, variant; har bir foydalanuvchi bir marta; to'lov jarayonidagi buyurtmalar 30 daqiqa joy band qiladi; 100% — bepul faollashtirish;
  - ⏳ yarim qolgan to'lov eslatmasi (Sozlamalar → Yopiq Premium guruh);
  - paneldagi ketma-ket xabarnomalar (flash) yo'qolib qolishi tuzatildi.
- **v2.3:**
  - tarif oynasida (1-tarif) «Sotib olish» ostida «🎬 Namuna darsni ko'rish» tugmasi;
  - promokod limiti to'lov bilan to'lganda shu promokodli to'lanmagan buyurtmalar avtomatik bekor qilinadi, foydalanuvchiga «Sotib olish» tugmali xabar boradi;
  - Payme tekshiruvida ham promokod qayta tekshiriladi: joyi boshqaga o'tgan eski buyurtma bekor qilinadi, pul olinmaydi;
  - promokod nofaol qilinsa, o'chirilsa yoki muddati o'tsa ham to'lanmagan buyurtmalar bekor qilinadi (har 5 daqiqada fon tekshiruvi);
  - qo'llangan promokod amal qilmay qolsa, bot to'liq narxda jimgina buyurtma yaratmaydi — sababini aytib, narxlarni qayta ko'rsatadi.
- **v2.4:**
  - promokod muddati soat/daqiqagacha belgilanadi; muddat tugashi bilan (1 daqiqa ichida) promokod avtomatik o'chadi, to'lanmagan buyurtmalari bekor bo'ladi, foydalanuvchilarga va adminga xabar boradi;
  - panelda muddatni o'zgartirish/uzaytirish (✏️) — uzaytirilsa promokod qayta faol bo'ladi;
  - o'tgan sana bilan promokod yaratib bo'lmaydi.
- **v2.1:** «Obuna sotib olish» asosiy menyudan olindi, sotib olish oynasida obuna haqida batafsil ma'lumot.
- **v2.0:**
  - telefon majburiy (faqat tugma orqali);
  - bepul dars, bepul materiallar va FAQ botdan olib tashlandi;
  - 4 ta yangi tarif, narxlar paneldan kiritiladi;
  - Payme Merchant API;
  - yopiq guruhni avtomatik boshqarish;
  - «👤 Mening obunam» bo'limi;
  - «🎓 AI mentor» (OpenAI vector store, kuniga 3 ta bepul savol, obunachilarga cheksiz);
  - operator xabarida sarlavha, yangi yopish matni, ixcham baho tugmalari;
  - panelga Telegram kod orqali kirish;
  - panelga «💎 Obunachilar», «💳 To'lovlar», «🩺 Tizim holati» bo'limlari qo'shildi.
- **v1.1:** chat tarixida leadning har bir harakati ko'rinadi.
- **v1.0:** birinchi versiya.
