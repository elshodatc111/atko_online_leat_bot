# ATKO Lead platforma — Telegram bot + operator/admin veb-paneli

ATKO Koreys Tili O'quv Markazi uchun leadlarni yig'uvchi **Telegram bot** (o'zbek va rus tillarida, OpenAI bilan) va operatorlar ishlaydigan **veb-panel**. Ikkalasi bitta dasturda ishlaydi.

- Python **3.14** (3.14.7 da sinovdan o'tgan)
- aiogram 3 (bot), FastAPI + Jinja2 + HTMX (panel), SQLite (baza), OpenAI (AI)

---

## 1. Imkoniyatlar

### Telegram bot (leadlar uchun)
| Bo'lim | Tavsif |
|---|---|
| Ro'yxatdan o'tish | Til (🇺🇿/🇷🇺) → ism → **«📱 Kontaktni ulashish»** tugmasi → maqsad → format. Qisqa va aniq |
| 📚 Kurslar va tariflar | Guruh, individual va gibrid tariflar (paneldan tahrirlanadi). Narx aytilmaydi — menejerga yo'naltiradi |
| 🎁 Bepul 1-dars | Telefon so'raydi → operator navbatiga tushadi |
| 📄 Bepul materiallar | Paneldan yuklangan PDF'lar (yuklab olish uchun telefon talab qilinadi — lead magnet) |
| ❓ Ko'p so'raladigan savollar | Admin tasdiqlagan FAQ |
| 🎓 Tutor | Koreys tili bo'yicha AI-o'qituvchi: grammatika, uyga vazifani tekshirish (matn/rasm/ovoz), mini-testlar. Yuklangan darsliklardan foydalanadi. O'quvchilar uchun cheksiz, boshqalar uchun kunlik limit |
| 👨‍💼 Operator bilan bog'lanish | Ish vaqtida: «2–10 daqiqada ulanadi». Ish vaqtidan tashqari: navbatga qo'yadi, AI javob berib turadi |
| 🤖 AI-konsultant | Istalgan savolga bilimlar bazasi asosida javob beradi, lead ma'lumotlarini avtomatik to'ldiradi, shikoyat/murakkab savolda operatorga ulaydi |
| 🎙 Ovozli xabarlar | Matnga o'giriladi (AI tushunadi, operator panelda matnini ham ko'radi) |
| ⭐ Baho | Chat yopilgach 1–5 yulduz + ixtiyoriy izoh. 1–2 baho — adminga darhol xabar |
| ⏰ Avto-eslatmalar | 1-, 3-, 7-kun (tahrirlanadi). Kursga qabul qilingan yoki rad etganlarga to'xtaydi |

### Veb-panel (operatorlar)
- **Chatlar**: navbat / mening / faol / yopilgan. **«✋ Menga ochdim»** — chatni olish; boshqa operatorlar «🔒 Dilnoza suhbatlashmoqda» deb ko'radi.
- Matn, rasm, audio, video, fayl almashish (hajm cheklovi bilan), brauzerdan **ovozli xabar yozish**.
- Leadning audiolarini eshitish, rasmlarini kattalashtirib ko'rish, ovozli xabar matni.
- **🔁 O'tkazish** — chatni boshqa operatorga berish. **🔒 Chatni yopish** — leadga operator nomidan xabar boradi.
- Tayyor javob shablonlari, **🤖 AI javob taklifi**, AI xulosa (lead kim, nima istaydi, qaysi tarif mos).
- Lead kartasi: status (✅ **Kursga qabul qilindi** va boshqalar), izohlar (xulosa), to'liq suhbat tarixi, 📞 qo'ng'iroq tugmasi.
- Bildirishnomalar: brauzer (ovozli signal bilan) + operatorning shaxsiy **Telegrami** (onlayn bo'lsa).
- Bir operatorda maksimal **5 ta** faol chat (sozlanadi).
- **Kechikish nazorati**: murojaatni 10 daqiqada hech kim olmasa — adminga xabar; faol chatda operator 5 daqiqa javob bermasa — operatorga va adminga ogohlantirish.

### Admin paneli
- 👨‍💼 **Operatorlar**: qo'shish (taklif havolasi orqali), o'chirish/tiklash, leadga ko'rinadigan ism, statistika.
- 📈 **Statistika**: kunlik va oylik — grafik va jadval ko'rinishida (operatorlar, leadlar, manbalar, konversiya, baho, javob tezligi).
- 🔗 **Manba havolalari**: `t.me/bot?start=instagram` kabi havolalar + QR-kod, har bir manba bo'yicha statistika.
- 📣 **Ommaviy xabar**: barcha / kursga qabul qilinganlar / qabul qilinmaganlar; matn, matn+rasm, matn+video; avval o'zingizga sinov.
- 💡 **FAQ**: AI ko'p so'ralgan savollarni guruhlab, javob loyihasini tayyorlaydi → admin tasdiqlasa botga qo'shiladi. Javobsiz savollar ro'yxati.
- 📚 Tariflar, ℹ️ Markaz ma'lumotlari, 📄 Materiallar, ⏰ Eslatmalar, 🧩 Shablonlar, ✏️ Bot matnlari — hammasi paneldan tahrirlanadi.
- 📑 **Excel eksport** (leadlar, chatlar, operatorlar, harakatlar jurnali, savollar) — fayl **bot orqali Telegramga** yuboriladi.
- 🧾 **Harakatlar jurnali** (+ Excel).
- ⚙️ **Sozlamalar**: ish vaqti, dam olish (yakshanba) va bayram kunlari, limitlar, fayl hajmlari, OpenAI modeli, **kunlik AI token limiti**, taxminiy xarajat.

---

## 2. Kompyuterda (Windows) ishga tushirish

### 2.1. Tayyorgarlik
1. **Bot yarating**: Telegramda [@BotFather](https://t.me/BotFather) → `/newbot` → tokenni nusxalang.
2. **Telegram ID ingizni** bilib oling: bot ishga tushgach unga `/myid` yozing (yoki [@userinfobot](https://t.me/userinfobot)).
3. **OpenAI kaliti**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

### 2.2. O'rnatish
1. ZIP ni oching, masalan `C:\KoreysTlilOnline\atko_lead_platform`.
2. **`install.bat`** faylini ikki marta bosing — virtual muhit yaratiladi va kutubxonalar o'rnatiladi. Oxirida `.env` fayli Notepad'da ochiladi.
3. `.env` faylini to'ldiring:
   ```
   BOT_TOKEN=bot_tokeningiz
   ADMIN_TG_IDS=sizning_telegram_id
   OPENAI_API_KEY=sk-...
   SECRET_KEY=istalgan-uzun-tasodifiy-matn
   ```
4. **`start.bat`** ni ishga tushiring. Brauzerda oching: **http://localhost:8000**
5. «✈️ Telegram orqali kirish» → botda «✅ Kirishni tasdiqlash» → panel ochiladi.

> Qo'lda: `py -3.14 -m venv .venv` → `.venv\Scripts\activate` → `pip install -r requirements.txt` → `python run.py`

### 2.3. Birinchi qadamlar (admin)
1. **ℹ️ Markaz ma'lumotlari** — `[TO'LDIRILSIN]` joylarni to'ldiring (manzil, telefon, kurs davomiyligi va h.k.). AI bu ma'lumotlarsiz javob bermaydi, menejerga yo'naltiradi.
2. **📚 Tariflar** — nomlar va tavsiflarni tekshiring.
3. **👨‍💼 Operatorlar** — operator qo'shing → taklif havolasini unga yuboring → u havolani bosib ro'yxatdan o'tadi.
4. **🔗 Manba havolalari** — Instagram, Telegram kanal va boshqalar uchun havola yarating.
5. **📄 Materiallar** — bepul PDF darsliklarni yuklang.
6. **⚙️ Sozlamalar** → «AI ga sinov so'rovi yuborish» — AI ishlayotganini tekshiring. **Kunlik token limitini** belgilang.

---

## 3. alwaysdata.com serveriga joylash

1. **Hisob** oching va panelda **Environment → Python** versiyasini **3.14** qiling.
2. Loyihani serverga yuklang (SFTP yoki SSH orqali), masalan `~/atko`.
3. **SSH** orqali:
   ```bash
   cd ~/atko
   python3.14 -m venv .venv          # yoki: python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env && nano .env
   ```
4. `.env` da server uchun:
   ```
   BOT_MODE=webhook
   WEBHOOK_BASE_URL=https://SIZNING-SAYT.alwaysdata.net
   WEBHOOK_SECRET=uzun-tasodifiy-matn
   PANEL_URL=https://SIZNING-SAYT.alwaysdata.net
   HOST=
   PORT=
   ```
   (`HOST` va `PORT` ni bo'sh qoldiring — alwaysdata `$IP` va `$PORT` ni o'zi beradi.)
5. **Web → Sites → Add a site**:
   - Type: **User program**
   - Command: `/home/LOGIN/atko/.venv/bin/python run.py`
   - Working directory: `/home/LOGIN/atko`
6. Saytni ishga tushiring va `https://SIZNING-SAYT.alwaysdata.net/health` ni oching — `{"ok": true}` chiqishi kerak.

**Muhim:**
- Dastur **bitta jarayonda** ishlashi kerak (bot, WebSocket va fon vazifalari birga). Bir nechta worker yoqmang.
- Kompyuterdagi ma'lumotlarni ko'chirish uchun `data` papkasini (baza + fayllar) serverdagi `data` papkasiga ko'chiring. Fayl yo'llari mutlaq saqlanadi, shuning uchun yangi joyda boshidan boshlash eng oson yo'l.
- Serverga o'tgach, kompyuterdagi botni to'xtating (bitta token ikki joyda ishlamaydi).
- Agar proksi WebSocket'ni o'tkazmasa, panel avtomatik ravishda har 20 soniyada yangilanish rejimiga o'tadi.

---

## 4. Tuzilishi

```
atko_lead_platform/
├─ run.py                 # ishga tushirish
├─ requirements.txt
├─ .env.example           # sozlamalar namunasi
├─ install.bat / start.bat
├─ data/                  # (avtomatik) atko.db, media/, exports/
└─ app/
   ├─ main.py             # FastAPI + bot + fon vazifalari
   ├─ config.py, db.py, models.py, seed.py
   ├─ bot/                # Telegram bot (aiogram 3)
   │  ├─ texts.py         # o'zbek/rus matnlar
   │  ├─ keyboards.py, actions.py, common.py, setup.py
   │  └─ handlers/        # start, menu, messages
   ├─ services/           # biznes-mantiq
   │  ├─ ai.py            # OpenAI: konsultant, tutor, transkripsiya, FAQ tahlili, xulosa
   │  ├─ chats.py         # operator chatlari
   │  ├─ scheduler.py     # kechikish nazorati, eslatmalar, FAQ avto-tahlil
   │  ├─ stats.py, excel.py, broadcast.py, knowledge.py, notify.py, ...
   └─ web/                # veb-panel
      ├─ routes/          # auth, dashboard, chats, leads, admin, content
      ├─ templates/       # Jinja2 sahifalar
      └─ static/          # CSS, JS, Chart.js, HTMX
```

## 5. OpenAI qanday ishlatiladi

| Funksiya | Qayerda |
|---|---|
| AI-konsultant (function calling: lead ma'lumotini saqlash, operatorga ulash, javobsiz savolni belgilash) | Bot, konsultant rejimi |
| AI-tutor (rasmni ko'rish, darsliklardan qidiruv — embeddings) | Bot, tutor rejimi |
| Mini-test generatsiyasi | Bot, tutor |
| Ovozli xabarni matnga o'girish | Bot va panel |
| Lead xulosasi va qiziqish darajasi (🔥/🌤/❄️) | Panel, chat olinganda |
| Operatorga javob taklifi | Panel, «🤖 AI taklif» |
| Savollarni guruhlash → FAQ takliflari | Panel, har kuni avtomatik yoki qo'lda |

Modellar **Sozlamalar** bo'limida o'zgartiriladi. Kunlik token limiti tugasa, AI ertasi kungacha o'chadi va bot oddiy tugmali rejimda ishlashda davom etadi.

## 6. Muammolar

| Muammo | Yechim |
|---|---|
| Panelga kira olmayapman | `.env` dagi `ADMIN_TG_IDS` to'g'rimi? Botga `/myid` yozib tekshiring. Dasturni qayta ishga tushiring |
| Bot javob bermayapti | `BOT_TOKEN` to'g'rimi? Konsolda xatolar bormi? Token boshqa joyda (serverda) ishlamayaptimi? |
| AI javob bermayapti | Sozlamalar → «AI ga sinov so'rovi yuborish». Kalit, model nomi va kunlik limitni tekshiring |
| Brauzer bildirishnomasi kelmayapti | Yuqoridagi «🔔 Bildirishnomalarni yoqish» tugmasini bosing va ruxsat bering |
| Operator ovozli xabari audio fayl bo'lib boradi | Bu normal (ffmpeg o'rnatilmagan). Xohlasangiz ffmpeg o'rnating — «voice» bo'lib boradi |

## 7. O'zgarishlar tarixi

- **v1.1** — Operator chatida leadning **har bir** harakati ko'rinadi: yozgan matnlari, ro'yxatdan o'tishda kiritgan ismi, yuborgan kontakti, bosgan menyu va inline tugmalari (🔘), `/start` buyrug'i, baho izohi, rad etilgan katta fayllar. Tugma bosishlari chatda «tugma» belgisi bilan ajratib ko'rsatiladi.
- **v1.0** — Birinchi versiya.
