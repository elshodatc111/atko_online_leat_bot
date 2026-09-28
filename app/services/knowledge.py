"""Bilimlar bazasi: kurs ma'lumotlari (AI uchun matn) va materiallar (PDF) indeksatsiyasi."""
from __future__ import annotations

import logging
import math
from pathlib import Path

from sqlalchemy import delete, select

from ..db import session_scope
from ..models import Faq, InfoPage, Material, MaterialChunk, Tariff
from . import settings, worktime

log = logging.getLogger(__name__)

CATEGORY_LABELS = {"group": "Guruh tariflari", "individual": "Individual (1-ga-1) tariflar", "hybrid": "Gibrid ta'lim"}


async def course_knowledge(lang: str = "uz") -> str:
    """AI konsultant uchun to'liq bilimlar bazasi matni."""
    async with session_scope() as s:
        tariffs = (await s.execute(select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.sort, Tariff.id))).scalars().all()
        pages = (await s.execute(select(InfoPage).order_by(InfoPage.sort, InfoPage.id))).scalars().all()
        faqs = (await s.execute(select(Faq).where(Faq.is_active.is_(True)).order_by(Faq.sort, Faq.id))).scalars().all()
    days_off = await settings.get("days_off") or []
    off_names = ", ".join(worktime.WEEKDAYS_UZ[d] for d in days_off) or "yo'q"
    parts: list[str] = []
    parts.append("## OPERATORLAR ISH VAQTI\n"
                 f"{await worktime.work_hours_text()} (Toshkent vaqti). Dam olish: {off_names} va bayram kunlari.")
    for cat in ("group", "individual", "hybrid"):
        items = [x for x in tariffs if x.category == cat]
        if not items:
            continue
        parts.append(f"## {CATEGORY_LABELS[cat].upper()}")
        for x in items:
            name = x.name_ru if lang == "ru" else x.name_uz
            desc = x.desc_ru if lang == "ru" else x.desc_uz
            parts.append(f"### {name}\n{desc}")
    for p in pages:
        title = p.title_ru if lang == "ru" else p.title_uz
        body = p.body_ru if lang == "ru" else p.body_uz
        parts.append(f"## {title.upper()}\n{body}")
    if faqs:
        parts.append("## KO'P SO'RALADIGAN SAVOLLAR (TASDIQLANGAN JAVOBLAR)")
        for f in faqs:
            q = f.q_ru if lang == "ru" else f.q_uz
            a = f.a_ru if lang == "ru" else f.a_uz
            parts.append(f"S: {q}\nJ: {a}")
    return "\n\n".join(parts)


# ------------------------------------------------------------------ PDF materiallar


def extract_pdf_text(path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            txt = ""
        txt = " ".join(txt.split())
        if txt:
            pages.append((i, txt))
    return pages


def chunk_pages(pages: list[tuple[int, str]], size: int = 1200, overlap: int = 150) -> list[tuple[int, str]]:
    chunks: list[tuple[int, str]] = []
    for page_no, text in pages:
        start = 0
        while start < len(text):
            piece = text[start : start + size]
            if piece.strip():
                chunks.append((page_no, piece))
            if start + size >= len(text):
                break
            start += size - overlap
    return chunks


async def index_material(material_id: int) -> None:
    """PDF matnini ajratib, OpenAI embedding bilan indekslaydi (tutor uchun)."""
    from . import ai

    async with session_scope() as s:
        m = await s.get(Material, material_id)
        if not m:
            return
        path = Path(m.file_path)
        m.index_status = "pending"
    try:
        if path.suffix.lower() == ".pdf":
            pages = extract_pdf_text(path)
        elif path.suffix.lower() in {".txt", ".md"}:
            pages = [(1, " ".join(path.read_text("utf-8", errors="ignore").split()))]
        else:
            pages = []
        chunks = chunk_pages(pages)
        if not chunks:
            raise ValueError("Fayldan matn ajratib bo'lmadi (skanerlangan PDF bo'lishi mumkin)")
        vectors: list[list[float] | None] = [None] * len(chunks)
        if await ai.is_available():
            batch = 64
            for i in range(0, len(chunks), batch):
                part = [c[1] for c in chunks[i : i + batch]]
                embs = await ai.embed(part)
                for j, e in enumerate(embs):
                    vectors[i + j] = e
        async with session_scope() as s:
            await s.execute(delete(MaterialChunk).where(MaterialChunk.material_id == material_id))
            for (page_no, text), vec in zip(chunks, vectors):
                s.add(MaterialChunk(material_id=material_id, page=page_no, text=text, embedding=vec))
            m = await s.get(Material, material_id)
            if m:
                m.index_status = "done"
                m.index_error = None if all(v is not None for v in vectors) else "Embedding yo'q (AI o'chiq) — kalit so'z qidiruvi ishlatiladi"
                m.chunks_count = len(chunks)
    except Exception as e:  # noqa: BLE001
        log.exception("Material indekslash xatosi")
        async with session_scope() as s:
            m = await s.get(Material, material_id)
            if m:
                m.index_status = "error"
                m.index_error = str(e)[:500]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def search_materials(query: str, k: int = 4) -> list[tuple[str, int | None, str]]:
    """Tutor uchun eng mos material bo'laklarini qaytaradi: (material nomi, sahifa, matn)."""
    from . import ai

    async with session_scope() as s:
        rows = (
            await s.execute(
                select(MaterialChunk, Material.title)
                .join(Material, Material.id == MaterialChunk.material_id)
                .where(Material.for_tutor.is_(True), Material.index_status == "done")
            )
        ).all()
    if not rows:
        return []
    scored: list[tuple[float, str, int | None, str]] = []
    qvec = None
    if any(r[0].embedding for r in rows) and await ai.is_available():
        try:
            qvec = (await ai.embed([query]))[0]
        except Exception:  # noqa: BLE001
            qvec = None
    words = {w.lower() for w in query.split() if len(w) > 1}
    for chunk, title in rows:
        if qvec is not None and chunk.embedding:
            score = _cos(qvec, chunk.embedding)
        else:
            low = chunk.text.lower()
            score = sum(1 for w in words if w in low) / (len(words) or 1)
        scored.append((score, title, chunk.page, chunk.text))
    scored.sort(key=lambda x: x[0], reverse=True)
    threshold = 0.25 if qvec is not None else 0.2
    return [(t, p, txt) for sc, t, p, txt in scored[:k] if sc >= threshold]
