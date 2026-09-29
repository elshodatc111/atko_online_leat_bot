"""Kam xotirali rejim (LOW_MEMORY=1) — bepul hosting (masalan, alwaysdata 256 MB RAM) uchun.

Muammo: aiogram ishga tushishda ~630 ta Telegram turi va metodining pydantic validatorlarini oldindan quradi
(~90 MB xotira va sekin start). Bu rejimda validatorlar kechiktiriladi (pydantic `defer_build`) va faqat
haqiqatan ishlatilgan turlar uchun, birinchi kerak bo'lganda quriladi. Natija: ~218 MB → ~130 MB, start 2 barobar tez.

Xavfsizlik: bog'liq turlar nomlari (forward ref) oldindan har bir modelga beriladi, shuning uchun kechiktirilgan
qurilish xuddi odatdagidek ishlaydi. `verify()` barcha modellarni bir martada qurib tekshiradi (sinovlarda).
"""
from __future__ import annotations

import typing

_enabled = False


def enable() -> None:
    """aiogram import qilinishidan OLDIN chaqirilishi kerak (app/__init__.py)."""
    global _enabled
    if _enabled:
        return
    from pydantic import BaseModel
    from pydantic._internal import _model_construction as mc

    BaseModel.model_config["defer_build"] = True
    original = BaseModel.model_rebuild.__func__

    def lazy_rebuild(cls, *, force=False, raise_errors=True, _parent_namespace_depth=2, _types_namespace=None):
        # aiogram import paytida barcha turlarni majburan quradi — o'rniga faqat nomlar maydonini saqlaymiz
        if _types_namespace is not None and not force and cls.model_config.get("defer_build") and not cls.__pydantic_complete__:
            ns = mc.unpack_lenient_weakvaluedict(cls.__pydantic_parent_namespace__) or {}
            ns.update(_types_namespace)
            cls.__pydantic_parent_namespace__ = ns
            return None
        return original(cls, force=force, raise_errors=raise_errors,
                        _parent_namespace_depth=_parent_namespace_depth + 1, _types_namespace=_types_namespace)

    BaseModel.model_rebuild = classmethod(lazy_rebuild)
    _enabled = True

    # aiogram turlari va metodlarini hozir yuklab, har biriga to'liq nomlar maydonini beramiz
    import aiogram.methods as methods
    import aiogram.types as types
    from aiogram.client.default import Default

    ns = {k: v for k, v in vars(types).items() if not k.startswith("_")}
    ns.update({k: v for k, v in vars(methods).items() if not k.startswith("_")})
    ns.update({"List": list, "Optional": typing.Optional, "Union": typing.Union, "Literal": typing.Literal, "Default": Default})
    for cls in _aiogram_models():
        if not cls.__pydantic_complete__:
            cur = mc.unpack_lenient_weakvaluedict(cls.__pydantic_parent_namespace__) or {}
            cls.__pydantic_parent_namespace__ = {**ns, **cur}


def _aiogram_models() -> set:
    from pydantic import BaseModel

    out: set = set()

    def walk(c):
        for sub in c.__subclasses__():
            if sub not in out:
                out.add(sub)
                walk(sub)

    walk(BaseModel)
    return {c for c in out if c.__module__.startswith("aiogram")}


def is_enabled() -> bool:
    return _enabled


def verify() -> list[str]:
    """Barcha kechiktirilgan aiogram modellarini qurib ko'radi. Xato bo'lganlar ro'yxatini qaytaradi (sinov uchun)."""
    bad = []
    for cls in sorted(_aiogram_models(), key=lambda c: c.__qualname__):
        if cls.__pydantic_complete__:
            continue
        try:
            cls.model_rebuild(raise_errors=True)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{cls.__module__}.{cls.__qualname__}: {e}")
    return bad
