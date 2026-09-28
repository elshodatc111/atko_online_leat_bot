"""Bot klaviaturalari."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from ..models import FORMATS, GOALS, Lead
from .texts import t


def ib(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[ib("🇺🇿 O'zbekcha", "lang:uz"), ib("🇷🇺 Русский", "lang:ru")]])


def contact_kb(lang: str) -> ReplyKeyboardMarkup:
    """Telefon raqam faqat shu tugma orqali qabul qilinadi (majburiy)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_contact", lang), request_contact=True)]],
        resize_keyboard=True, is_persistent=True,
    )


def goal_kb(lang: str) -> InlineKeyboardMarkup:
    keys = list(GOALS.keys())
    rows = [[ib(GOALS[k][lang], f"goal:{k}") for k in keys[i : i + 2]] for i in range(0, len(keys), 2)]
    rows.append([ib(t("skip", lang), "goal:skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [[ib(FORMATS[k][lang], f"fmt:{k}") for k in FORMATS], [ib(t("skip", lang), "fmt:skip")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu(lead: Lead, tutor_enabled: bool = True) -> ReplyKeyboardMarkup:
    lang = lead.lang
    B = lambda k: KeyboardButton(text=t(k, lang))  # noqa: E731
    if not lead.phone:
        return contact_kb(lang)
    if lead.mode == "tutor":
        rows = [[B("btn_quiz"), B("btn_mysub")], [B("btn_consultant"), B("btn_operator")]]
    else:
        rows = [
            [B("btn_courses"), B("btn_buy")],
            [B("btn_mysub")] + ([B("btn_tutor")] if tutor_enabled else []),
            [B("btn_operator")],
            [B("btn_info"), B("btn_lang")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="✍️ ...")


def cta_kb(lang: str, operator: bool = True, buy: bool = True) -> InlineKeyboardMarkup | None:
    rows = []
    if buy:
        rows.append([ib(t("btn_buy", lang), "buy")])
    if operator:
        rows.append([ib(t("operator_btn_inline", lang), "cta:operator")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def quiz_level_kb(lang: str) -> InlineKeyboardMarkup:
    ru = lang == "ru"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("TOPIK I — 1" if not ru else "TOPIK I — 1 ур.", "quiz:lvl:beginner"),
         ib("TOPIK I — 2" if not ru else "TOPIK I — 2 ур.", "quiz:lvl:elementary")],
        [ib("TOPIK II — 3-4" if not ru else "TOPIK II — 3-4 ур.", "quiz:lvl:intermediate"),
         ib("EPS-TOPIK", "quiz:lvl:eps")],
    ])


def skip_comment_kb(chat_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[ib(t("skip", lang), f"rate_skip:{chat_id}")]])
