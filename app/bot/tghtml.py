"""Telegram HTML matnini tekshirish va xavfsiz variantga o'tkazish.

Telegram faqat cheklangan teglarni qabul qiladi; noto'g'ri teg (masalan, «<b/b>») bo'lsa xabar umuman yuborilmaydi.
"""
from __future__ import annotations

import html
import re

ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "tg-spoiler", "span", "blockquote", "tg-emoji"}
_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[a-zA-Z-]+(?:=(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*>")
_ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|lt|gt|amp|quot);")


def error(text: str) -> str | None:
    """Matn Telegram HTML sifatida to'g'ri bo'lsa None, aks holda xato sababi."""
    stack: list[str] = []
    pos = 0
    s = text or ""
    while True:
        i = s.find("<", pos)
        j = s.find("&", pos)
        if j != -1 and (i == -1 or j < i):
            if not _ENTITY.match(s, j):
                return "«&» belgisi — uning o'rniga «&amp;» yozing"
            pos = j + 1
            continue
        if i == -1:
            break
        m = _TAG.match(s, i)
        if not m:
            frag = s[i:i + 12].split("\n")[0]
            return f"noto'g'ri teg: «{frag}» (oddiy «<» belgisi uchun «&lt;» yozing)"
        closing, name = m.group(1) == "/", m.group(2).lower()
        if name not in ALLOWED:
            return f"Telegram qo'llamaydigan teg: «<{m.group(1)}{name}>» (ruxsat: b, i, u, s, code, pre, a, blockquote)"
        if closing:
            if not stack or stack[-1] != name:
                return f"yopilmagan yoki tartibi buzilgan teg: «</{name}>»"
            stack.pop()
        else:
            stack.append(name)
        pos = m.end()
    if stack:
        return f"yopilmagan teg: «<{stack[-1]}>»"
    return None


def to_plain(text: str) -> str:
    """Teglarni olib tashlab, oddiy matnga aylantiradi (HTML parse xatosida zaxira)."""
    return html.unescape(re.sub(r"<[^>]{0,200}>", "", text or ""))
