"""OpenAI integratsiyasi: konsultant, tutor (darsliklar — vector store), transkripsiya, xulosa, javob taklifi, testlar."""
from __future__ import annotations

import base64
import html
import json
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..config import config
from ..db import session_scope
from ..models import GOALS, AiUsage, Chat, Lead, Message
from . import knowledge, settings, worktime

log = logging.getLogger(__name__)

_client = None
_client_key: str | None = None


# ------------------------------------------------------------------ asosiy yordamchilar


async def api_key() -> str:
    return (await settings.get("openai_api_key") or "").strip() or config.OPENAI_API_KEY


async def get_client():
    global _client, _client_key
    key = await api_key()
    if not key:
        return None
    if _client is None or key != _client_key:
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(api_key=key, timeout=90, max_retries=2)
        _client_key = key
    return _client


async def usage_today() -> AiUsage:
    today = worktime.now_local().date()
    async with session_scope() as s:
        row = await s.get(AiUsage, today)
        if row is None:
            row = AiUsage(day=today, requests=0, input_tokens=0, output_tokens=0, audio_seconds=0, errors=0)
        return row


async def limit_reached() -> bool:
    limit = int(await settings.get("ai_daily_token_limit") or 0)
    if limit <= 0:
        return False
    u = await usage_today()
    return (u.input_tokens + u.output_tokens) >= limit


async def is_available() -> bool:
    if not await settings.get("ai_enabled"):
        return False
    if not await api_key():
        return False
    return not await limit_reached()


async def _record(inp: int = 0, out: int = 0, error: bool = False, audio: float = 0) -> None:
    today = worktime.now_local().date()
    async with session_scope() as s:
        row = await s.get(AiUsage, today)
        if row is None:
            row = AiUsage(day=today, requests=0, input_tokens=0, output_tokens=0, audio_seconds=0, errors=0)
            s.add(row)
        row.requests = (row.requests or 0) + 1
        row.input_tokens = (row.input_tokens or 0) + inp
        row.output_tokens = (row.output_tokens or 0) + out
        row.audio_seconds = (row.audio_seconds or 0) + audio
        if error:
            row.errors = (row.errors or 0) + 1


async def estimate_cost(inp: int, out: int) -> float:
    pi = float(await settings.get("ai_price_input_per_1m") or 0)
    po = float(await settings.get("ai_price_output_per_1m") or 0)
    return inp / 1_000_000 * pi + out / 1_000_000 * po


class AIUnavailable(Exception):
    pass


async def complete(messages: list[dict], *, tools: list[dict] | None = None, max_tokens: int = 2500,
                   json_mode: bool = False, model: str | None = None) -> Any:
    """chat.completions chaqiruvi. Model qo'llamaydigan parametrlarni avtomatik olib tashlaydi."""
    if not await is_available():
        raise AIUnavailable()
    client = await get_client()
    kwargs: dict[str, Any] = {
        "model": model or await settings.get("ai_model"),
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }
    effort = (await settings.get("ai_reasoning_effort") or "").strip()
    if effort:
        kwargs["reasoning_effort"] = effort
    if tools:
        kwargs["tools"] = tools
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    from openai import BadRequestError

    for _ in range(4):
        try:
            resp = await client.chat.completions.create(**kwargs)
            u = getattr(resp, "usage", None)
            await _record(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
            return resp.choices[0].message
        except BadRequestError as e:
            msg = str(e).lower()
            if "reasoning_effort" in msg and "reasoning_effort" in kwargs:
                kwargs.pop("reasoning_effort")
                continue
            if "max_completion_tokens" in msg and "max_completion_tokens" in kwargs:
                kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
                continue
            if "response_format" in msg and "response_format" in kwargs:
                kwargs.pop("response_format")
                continue
            await _record(error=True)
            raise
        except Exception:
            await _record(error=True)
            raise
    raise AIUnavailable()




async def transcribe(path: str | Path, lang: str | None = None) -> str | None:
    if not await settings.get("ai_transcribe_voice") or not await is_available():
        return None
    client = await get_client()
    p = Path(path)
    name = p.name
    if p.suffix.lower() in {".oga", ".opus"}:
        name = p.stem + ".ogg"
    try:
        with p.open("rb") as fh:
            resp = await client.audio.transcriptions.create(
                model=await settings.get("ai_transcribe_model"), file=(name, fh.read()),
            )
        await _record(0, 0)
        text = getattr(resp, "text", None) or (resp if isinstance(resp, str) else None)
        return (text or "").strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning("Transkripsiya xatosi: %s", e)
        await _record(error=True)
        return None


# ------------------------------------------------------------------ formatlash

_ALLOWED = ("b", "i", "u", "s", "code", "pre")


def to_telegram_html(text: str) -> str:
    """AI javobini Telegram HTML formatiga xavfsiz o'tkazadi."""
    if not text:
        return ""
    text = text.strip()
    esc = html.escape(text, quote=False)
    for tag in _ALLOWED:
        esc = re.sub(rf"&lt;{tag}&gt;", f"<{tag}>", esc)
        esc = re.sub(rf"&lt;/{tag}&gt;", f"</{tag}>", esc)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc, flags=re.S)
    esc = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"<b>\1</b>", esc)
    esc = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", esc)
    # yopilmagan teglarni tekshirish
    for tag in _ALLOWED:
        if esc.count(f"<{tag}>") != esc.count(f"</{tag}>"):
            esc = esc.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
    return esc


def _lang_rule(lang: str) -> str:
    return "Javobni O'ZBEK tilida (lotin yozuvida) yozing. Agar foydalanuvchi kirill yozuvida yozsa, kirillda javob bering."


FORMAT_RULE = (
    "Format: Telegram uchun. Faqat <b>, <i>, <code> HTML teglaridan foydalaning, Markdown (**, ###) ishlatmang. "
    "Javoblar qisqa va o'qishga qulay bo'lsin (odatda 3-8 qator), kerak bo'lsa emoji ishlating."
)


async def _history(lead_id: int, mode: str, exclude_id: int | None, limit: int | None = None) -> list[dict]:
    limit = limit or int(await settings.get("ai_history_messages") or 12)
    async with session_scope() as s:
        q = select(Message).where(Message.lead_id == lead_id)
        if exclude_id:
            q = q.where(Message.id != exclude_id)
        if mode == "tutor":
            q = q.where(Message.mode == "tutor")
        else:
            q = q.where((Message.mode != "tutor") | (Message.mode.is_(None)))
        rows = (await s.execute(q.order_by(Message.id.desc()).limit(limit))).scalars().all()
    out: list[dict] = []
    for m in reversed(rows):
        content = m.text or m.transcript
        if not content:
            content = {"photo": "[rasm yubordi]", "voice": "[ovozli xabar]", "document": "[fayl]",
                       "video": "[video]", "audio": "[audio]"}.get(m.kind, "[xabar]")
        elif m.kind == "voice" and m.transcript and not m.text:
            content = f"[ovozli xabar]: {m.transcript}"
        if m.sender == "lead":
            out.append({"role": "user", "content": content})
        elif m.sender == "operator":
            out.append({"role": "assistant", "content": f"[Operator {m.staff.display_name if m.staff else ''}]: {content}"})
        elif m.sender in ("ai", "bot"):
            out.append({"role": "assistant", "content": content[:1500]})
    return out


def _image_part(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def _user_content(text: str | None, image_path: str | None) -> Any:
    if image_path:
        parts: list[dict] = [{"type": "text", "text": text or "Rasmni ko'rib chiqing."}]
        img = _image_part(image_path)
        if img:
            parts.append(img)
        return parts
    return text or ""


# ------------------------------------------------------------------ konsultant

CONSULTANT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_lead_info",
            "description": "Foydalanuvchi suhbatda o'zi haqida aytgan ma'lumotlarni lead kartasiga saqlash. Faqat aniq aytilgan ma'lumotlarni yozing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Ismi"},
                    "goal": {"type": "string", "enum": list(GOALS.keys())},
                    "study_format": {"type": "string", "enum": ["online", "offline", "hybrid"]},
                    "level": {"type": "string", "description": "Koreys tili darajasi (noldan, hangul, boshlang'ich, o'rta, yuqori, TOPIK N)"},
                    "city": {"type": "string"},
                    "interested_tariff": {"type": "string"},
                    "temperature": {"type": "string", "enum": ["hot", "warm", "cold"],
                                    "description": "Kursga yozilishga qiziqish darajasi"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_operator",
            "description": "Suhbatni jonli operatorga ulash: foydalanuvchi odam/operator bilan gaplashmoqchi bo'lsa, shikoyat, to'lov muammosi, jahl, murakkab shaxsiy masala, yoki kursga yozilishga tayyor bo'lsa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "enum": ["user_request", "complaint", "payment", "ready_to_enroll", "complex"]},
                    "summary": {"type": "string", "description": "Operator uchun qisqacha mazmun"},
                },
                "required": ["reason", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_gap",
            "description": "Foydalanuvchi savoliga bilimlar bazasida javob YO'Q bo'lsa chaqiring (masalan, [TO'LDIRILSIN] joylar yoki umuman yo'q ma'lumot).",
            "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
        },
    },
]


def _consultant_prompt(kb: str, lead: Lead, extra: str) -> str:
    known = []
    if lead.name:
        known.append(f"ism: {lead.name}")
    known.append("telefon: " + ("tasdiqlangan ✅" if lead.phone else "yo'q"))
    if lead.goal:
        known.append(f"maqsad: {lead.goal}")
    if lead.study_format:
        known.append(f"format: {lead.study_format}")
    if lead.level:
        known.append(f"daraja: {lead.level}")
    if lead.city:
        known.append(f"shahar: {lead.city}")
    return f"""Siz "ATKO Koreys Tili O'quv Markazi"ning rasmiy AI-konsultantisiz (Telegram bot). Koreys tili, TOPIK va EPS-TOPIK bo'yicha mutaxassissiz. Uslub: samimiy, professional, rag'batlantiruvchi, savodli.

{_lang_rule(lead.lang)}
{FORMAT_RULE}

MAQSAD: mijoz ehtiyojini tushunish (maqsad, daraja, vaqt, format), 1-2 ta mos tarifni sababi bilan tavsiya qilish va kursga yozilishga yo'naltirish.

TARIFLAR VA TO'LOV:
- Premium obuna (video darslar, yopiq Telegram guruh) — botda «📚 Tariflar va narxlar» → Premium → «💳 Sotib olish» (yoki «👤 Mening obunam» → «Uzaytirish») orqali Payme bilan onlayn sotib olinadi. To'lovdan so'ng guruh havolasi avtomatik keladi. Premium obunachilar 🎓 AI mentordan cheksiz foydalanadi.
- Zoom guruh darslari va Individual darslar (hammasi Zoom orqali, har bir dars 120 daqiqa; 12 dars — haftasiga 3 ta, 20 dars — haftasiga 5 ta, 1 oy) — oldindan to'lov menejer orqali: foydalanuvchi tarif oynasida paketni tanlaydi, menejer bog'lanib to'lov va jadvalni kelishadi. Yoki «👨‍💼 Operator bilan bog'lanish» tugmasi.
- Narxlarni BILIMLAR BAZASIdagidek aniq ayting. Narx ko'rsatilmagan bo'lsa — "narxni menejerimiz aniqlab beradi" deng. Chegirma, promokod yoki narxni o'ylab topmang.
- BEPUL DARS YO'Q. Bepul dars, bepul material yoki sinov darsi va'da qilmang.

QOIDALAR:
1. Faqat quyidagi BILIMLAR BAZASIdagi ma'lumotga tayaning. Yo'q ma'lumotni O'YLAB TOPMANG. "[TO'LDIRILSIN]" belgisi — ma'lumot yo'q degani. Bunday holda "Bu bo'yicha aniq ma'lumotni menejerimiz beradi" deng va knowledge_gap funksiyasini chaqiring.
2. Telefon raqam allaqachon tasdiqlangan — uni so'ramang.
3. Kafolat bermang: imtihondan o'tish, ball, viza yoki Koreyada ish kafolatlanmaydi. EPS-TOPIK ro'yxatdan o'tish va ishga yuborish faqat rasmiy davlat idoralari orqali. ATKO faqat imtihonga TAYYORLAYDI.
4. Foydalanuvchi o'zi haqida ma'lumot aytsa (ism, maqsad, daraja, shahar, format, qiziqqan tarif) — save_lead_info ni chaqiring. Qiziqish darajasini ham baholang (temperature).
5. Foydalanuvchi operator/odam bilan gaplashmoqchi bo'lsa, shikoyat, to'lov muammosi, jahl yoki Zoom/Individual darslarga yozilishga tayyor bo'lsa — escalate_to_operator ni chaqiring va qisqa javob bering.
6. Raqobatchilar haqida salbiy gapirmang; siyosat va din mavzulariga kirmang.
7. Koreys tili bo'yicha savol bersa — qisqa, misollar bilan (koreyscha + tarjima) javob bering va batafsil yordam uchun «🎓 AI mentor» bo'limini tavsiya qiling.
8. Faqat birinchi xabarda salomlashing. Javob oxirida suhbatni davom ettiruvchi BITTA savol yoki taklif (Call-to-Action) bering.

MIJOZ HAQIDA MA'LUM MA'LUMOTLAR: {", ".join(known)}
{("QO'SHIMCHA KO'RSATMALAR (admin):" + chr(10) + extra) if extra else ""}

===== BILIMLAR BAZASI =====
{kb}
===== BILIMLAR BAZASI TUGADI ====="""


@dataclass
class AIResult:
    text: str = ""
    escalate: dict | None = None
    unanswered: bool = False
    lead_updates: dict[str, Any] = field(default_factory=dict)


async def _run_with_tools(messages: list[dict], tools: list[dict], result: AIResult) -> str:
    for _ in range(3):
        msg = await complete(messages, tools=tools)
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return msg.content or ""
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in calls
            ],
        })
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            name = c.function.name
            if name == "save_lead_info":
                result.lead_updates.update({k: v for k, v in args.items() if v})
            elif name == "escalate_to_operator":
                result.escalate = args
            elif name == "knowledge_gap":
                result.unanswered = True
            messages.append({"role": "tool", "tool_call_id": c.id, "content": "ok"})
    msg = await complete(messages)
    return msg.content or ""


async def consultant_reply(lead: Lead, text: str | None, image_path: str | None = None,
                           exclude_id: int | None = None) -> AIResult:
    kb = await knowledge.course_knowledge(lead.lang)
    extra = (await settings.get("ai_extra_instructions") or "").strip()
    messages: list[dict] = [{"role": "system", "content": _consultant_prompt(kb, lead, extra)}]
    messages += await _history(lead.id, "consultant", exclude_id)
    messages.append({"role": "user", "content": _user_content(text, image_path)})
    result = AIResult()
    result.text = await _run_with_tools(messages, CONSULTANT_TOOLS, result)
    return result


# ------------------------------------------------------------------ tutor


def _tutor_prompt(lead: Lead, context: str, is_student: bool) -> str:
    return f"""Siz "ATKO Koreys Tili O'quv Markazi"ning AI mentorisiz — koreys tili bo'yicha shaxsiy o'qituvchi-yordamchi. TOPIK va EPS-TOPIK bo'yicha mutaxassissiz.

{_lang_rule(lead.lang)}
{FORMAT_RULE}
Koreyscha misollar har doim hangulda yoziladi.

VAZIFA: o'quvchining koreys tilini haqiqatan o'rganishiga yordam berish.
- Darajani hisobga oling: boshlang'ich darajada koreyscha misol yoniga o'qilishini (romanizatsiya) yozing, o'rta/yuqori darajada yozmang.
- Grammatika tushuntirish tartibi: ma'nosi → qoida/yasalishi → 2-3 misol (koreyscha + tarjima) → keng uchraydigan xato.
- Talaffuz savollarida qoida nomini (bog'lanish, qattiqlashish, burunlashish va h.k.) ayting va misol keltiring.
- Uyga vazifani tekshirish (matn, rasm yoki ovozli xabar): har bir xato uchun ❌ xato → ✅ to'g'ri → 📌 qisqa qoida. Oxirida umumiy baho va 1-2 o'xshash mashq.
- O'quvchi o'rniga vazifani to'liq bajarib bermang: avval yo'naltiruvchi ishora bering, o'zi urinib ko'rishini so'rang, keyin tekshiring.
- So'ralganda darajaga mos test/mashq tuzing (TOPIK/EPS-TOPIK uslubida), javoblarni o'quvchi javob bergandan keyin tahlil qiling.
- Ishonchingiz komil bo'lmasa, ochiq ayting va o'qituvchi/mentordan tasdiqlatishni tavsiya qiling.
- Bu rejimda kurs sotmang va reklama qilmang. Koreys tilidan tashqari mavzularda muloyimlik bilan asosiy mavzuga qayting.
- Javob oxirida o'qishni davom ettiruvchi taklif bering (masalan, "Mustahkamlash uchun 3 ta mashq beraymi?").

O'QUVCHI: {"ATKO Premium obunachisi" if is_student else "bepul foydalanuvchi"}; daraja: {lead.level or "noma'lum"}.
{("ATKO DARSLIKLARI: savolga mos ma'lumotni file_search orqali darsliklardan qidiring va javobda ulardan foydalaning, manbani qisqa eslating." if context == "file_search" else "")}"""


async def vector_store_ids() -> list[str]:
    raw = str(await settings.get("ai_vector_store_ids") or "")
    return [x.strip() for x in raw.replace(";", ",").replace("\n", ",").split(",") if x.strip()]


def _responses_input(messages: list[dict]) -> list[dict]:
    """chat.completions formatidagi xabarlarni Responses API formatiga o'tkazadi."""
    out = []
    for m in messages:
        c = m["content"]
        if isinstance(c, list):
            parts = []
            for p in c:
                if p.get("type") == "text":
                    parts.append({"type": "input_text", "text": p["text"]})
                elif p.get("type") == "image_url":
                    parts.append({"type": "input_image", "image_url": p["image_url"]["url"]})
            out.append({"role": m["role"], "content": parts})
        else:
            out.append({"role": m["role"], "content": c})
    return out


async def respond_with_files(system: str, messages: list[dict], stores: list[str], max_tokens: int = 3500) -> str:
    """Responses API + file_search (OpenAI Storage'dagi darsliklar)."""
    if not await is_available():
        raise AIUnavailable()
    client = await get_client()
    kwargs: dict[str, Any] = {
        "model": await settings.get("ai_model"), "instructions": system, "input": _responses_input(messages),
        "tools": [{"type": "file_search", "vector_store_ids": stores, "max_num_results": 6}],
        "max_output_tokens": max_tokens,
    }
    effort = (await settings.get("ai_reasoning_effort") or "").strip()
    if effort:
        kwargs["reasoning"] = {"effort": effort}
    from openai import BadRequestError

    for _ in range(3):
        try:
            resp = await client.responses.create(**kwargs)
            u = getattr(resp, "usage", None)
            await _record(getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0)
            return getattr(resp, "output_text", "") or ""
        except BadRequestError as e:
            if "reasoning" in str(e).lower() and "reasoning" in kwargs:
                kwargs.pop("reasoning")
                continue
            await _record(error=True)
            raise
        except Exception:
            await _record(error=True)
            raise
    raise AIUnavailable()


async def tutor_reply(lead: Lead, text: str | None, image_path: str | None = None,
                      exclude_id: int | None = None, is_student: bool = False) -> str:
    stores = await vector_store_ids()
    history = await _history(lead.id, "tutor", exclude_id)
    user_msg = {"role": "user", "content": _user_content(text, image_path)}
    if stores:
        system = _tutor_prompt(lead, "file_search", is_student)
        try:
            return await respond_with_files(system, history + [user_msg], stores)
        except AIUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("file_search bilan javob bo'lmadi, oddiy rejimga o'tildi: %s", e)
    messages: list[dict] = [{"role": "system", "content": _tutor_prompt(lead, "", is_student)}]
    messages += history
    messages.append(user_msg)
    msg = await complete(messages, max_tokens=3500)
    return msg.content or ""


async def quiz_question(level: str, lang: str, avoid: list[str] | None = None) -> dict | None:
    level_desc = {"beginner": "boshlang'ich (TOPIK I, 1-daraja)", "elementary": "TOPIK I, 2-daraja",
                  "intermediate": "o'rta (TOPIK II, 3-4 daraja)", "eps": "EPS-TOPIK uslubida"}.get(level, level)
    avoid_txt = "\n".join(f"- {a}" for a in (avoid or [])[-10:])
    prompt = f"""Koreys tili bo'yicha {level_desc} darajadagi BITTA test savoli tuzing (grammatika, lug'at yoki o'qish).
Savol va izoh o'zbek (lotin) tilida, koreyscha qismlar hangulda.
4 ta javob varianti, faqat bittasi to'g'ri. Variantlar qisqa bo'lsin (60 belgidan oshmasin).
{("Quyidagi savollarni takrorlamang:" + chr(10) + avoid_txt) if avoid_txt else ""}
Faqat JSON qaytaring: {{"question": "...", "options": ["...","...","...","..."], "correct": 0, "explanation": "qisqa izoh"}}"""
    msg = await complete([{"role": "user", "content": prompt}], json_mode=True, max_tokens=2000)
    try:
        data = json.loads(_strip_json(msg.content or ""))
        opts = [str(o)[:60] for o in data.get("options", [])][:4]
        if len(opts) < 2:
            return None
        correct = int(data.get("correct", 0))
        if not 0 <= correct < len(opts):
            correct = 0
        return {"question": str(data.get("question", ""))[:900], "options": opts, "correct": correct,
                "explanation": str(data.get("explanation", ""))[:600]}
    except (ValueError, TypeError):
        return None


def _strip_json(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(json)?", "", s).rstrip("`").strip()
    return s


# ------------------------------------------------------------------ operator yordamchilari


async def _dialog_text(lead_id: int, limit: int = 40) -> str:
    async with session_scope() as s:
        rows = (await s.execute(select(Message).where(Message.lead_id == lead_id)
                                .order_by(Message.id.desc()).limit(limit))).scalars().all()
    who = {"lead": "Mijoz", "ai": "AI", "operator": "Operator", "system": "Tizim", "bot": "Bot"}
    lines = []
    for m in reversed(rows):
        content = m.text or m.transcript or f"[{m.kind}]"
        lines.append(f"{who.get(m.sender, m.sender)}: {content[:600]}")
    return "\n".join(lines)


async def summarize_lead(lead_id: int) -> dict | None:
    """Lead bo'yicha qisqa xulosa va qiziqish darajasi (operator chatni olganda ko'rinadi)."""
    if not await is_available():
        return None
    dialog = await _dialog_text(lead_id)
    if not dialog:
        return None
    prompt = f"""Quyida ATKO o'quv markazi boti va mijoz o'rtasidagi suhbat. Operator uchun o'zbek tilida qisqa xulosa yozing.
JSON qaytaring: {{"summary": "3-5 qatorli xulosa: kim, nima istaydi, maqsadi, darajasi, qaysi tarif mos, e'tiborga olinadigan jihatlar", "temperature": "hot|warm|cold"}}

SUHBAT:
{dialog}"""
    try:
        msg = await complete([{"role": "user", "content": prompt}], json_mode=True, max_tokens=1500)
        data = json.loads(_strip_json(msg.content or "{}"))
    except Exception as e:  # noqa: BLE001
        log.warning("Xulosa xatosi: %s", e)
        return None
    async with session_scope() as s:
        lead = await s.get(Lead, lead_id)
        if lead:
            lead.ai_summary = str(data.get("summary") or "")[:2000] or lead.ai_summary
            if data.get("temperature") in ("hot", "warm", "cold"):
                lead.temperature = data["temperature"]
    return data


async def suggest_reply(chat_id: int) -> str:
    async with session_scope() as s:
        chat = await s.get(Chat, chat_id)
        if not chat:
            return ""
        lead = chat.lead
        op_name = chat.operator.display_name if chat.operator else "Operator"
    kb = await knowledge.course_knowledge(lead.lang)
    dialog = await _dialog_text(lead.id, 25)
    prompt = f"""Siz ATKO o'quv markazi operatori ({op_name}) uchun javob loyihasini yozasiz.
Mijozning oxirgi xabariga mos, samimiy va professional javob yozing. {_lang_rule(lead.lang)}
Narxni aytmang (menejer individual hisoblaydi). Faqat bilimlar bazasidagi ma'lumotdan foydalaning. Faqat javob matnini qaytaring, HTML/Markdown ishlatmang.

BILIMLAR BAZASI:
{kb}

SUHBAT:
{dialog}"""
    msg = await complete([{"role": "user", "content": prompt}], max_tokens=1500)
    return (msg.content or "").strip()
