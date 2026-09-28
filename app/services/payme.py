"""Payme Merchant API (JSON-RPC) integratsiyasi.

Payme kassa sozlamalarida "Endpoint URL" sifatida:  {PANEL_URL}/payme
Hisob (account) maydoni nomi:  order_id  (panelda o'zgartirish mumkin)

Oqim: bot buyurtma (Payment, state=0) yaratadi → foydalanuvchi checkout.paycom.uz da to'laydi →
Payme serverimizga CheckPerformTransaction → CreateTransaction → PerformTransaction yuboradi →
PerformTransaction da obuna avtomatik faollashadi va guruh havolasi yuboriladi.
CancelTransaction (to'lovdan keyin) — pul qaytarilgan: obuna qisqartiriladi, kerak bo'lsa guruhdan chiqariladi.
"""
from __future__ import annotations

import base64
import hmac
import html
import logging
import time
from typing import Any

from sqlalchemy import select

from ..config import config
from ..db import session_scope, utcnow
from ..models import Lead, Payment, SubscriptionPlan
from . import settings
from .notify import hub, telegram_staff

log = logging.getLogger(__name__)

TIMEOUT_MS = 43_200_000  # 12 soat

last_request_at: float | None = None
last_error: str | None = None


def now_ms() -> int:
    return int(time.time() * 1000)


class PaymeError(Exception):
    def __init__(self, code: int, uz: str, ru: str | None = None, en: str | None = None, data: str | None = None):
        super().__init__(uz)
        self.code, self.data = code, data
        self.message = {"uz": uz, "ru": ru or uz, "en": en or uz}


# ------------------------------------------------------------------ sozlamalar


async def merchant_id() -> str:
    return (await settings.get("payme_merchant_id") or "").strip() or config.PAYME_MERCHANT_ID


async def test_mode() -> bool:
    return bool(await settings.get("payme_test_mode"))


async def active_key() -> str:
    if await test_mode():
        return (await settings.get("payme_test_key") or "").strip() or config.PAYME_TEST_KEY
    return (await settings.get("payme_key") or "").strip() or config.PAYME_KEY


async def is_configured() -> bool:
    return bool(await merchant_id() and await active_key())


async def account_field() -> str:
    return (await settings.get("payme_account_field") or "order_id").strip() or "order_id"


async def checkout_url(payment: Payment, lang: str = "uz") -> str:
    base = "https://test.paycom.uz" if await test_mode() else "https://checkout.paycom.uz"
    parts = [f"m={await merchant_id()}", f"ac.{await account_field()}={payment.id}", f"a={payment.amount * 100}",
             f"l={'ru' if lang == 'ru' else 'uz'}"]
    ret = (await settings.get("payme_return_url") or "").strip()
    if ret:
        parts.append(f"c={ret}")
    token = base64.b64encode(";".join(parts).encode()).decode()
    return f"{base}/{token}"


async def create_order(lead: Lead, plan_id: int) -> tuple[Payment, str]:
    async with session_scope() as s:
        plan = await s.get(SubscriptionPlan, plan_id)
        if not plan or not plan.is_active or plan.price <= 0:
            raise ValueError("Tarif varianti topilmadi yoki narxi belgilanmagan")
        tariff_name = plan.tariff.name_uz if plan.tariff else "ATKO Premium"
        p = Payment(lead_id=lead.id, tg_id=lead.tg_id, plan_id=plan.id, title=f"{tariff_name} — {plan.title_uz}",
                    days=plan.days, amount=plan.price, state=0, is_test=await test_mode())
        s.add(p)
        await s.flush()
        await s.refresh(p)
    return p, await checkout_url(p, lead.lang)


# ------------------------------------------------------------------ JSON-RPC


async def check_auth(header: str | None) -> bool:
    key = await active_key()
    if not header or not key or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode()
    except Exception:  # noqa: BLE001
        return False
    login, _, password = decoded.partition(":")
    return login == "Paycom" and hmac.compare_digest(password, key)


async def handle(body: dict[str, Any], auth_header: str | None) -> dict[str, Any]:
    global last_request_at, last_error
    last_request_at = time.time()
    req_id = body.get("id") if isinstance(body, dict) else None
    try:
        if not await check_auth(auth_header):
            raise PaymeError(-32504, "Avtorizatsiya xatosi", "Недостаточно привилегий", "Insufficient privilege")
        method = body.get("method")
        params = body.get("params") or {}
        handler = METHODS.get(method)
        if not handler:
            raise PaymeError(-32601, "Metod topilmadi", "Метод не найден", "Method not found", method)
        result = await handler(params)
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except PaymeError as e:
        if e.code != -32504:
            last_error = f"{e.code}: {e.message['uz']}"
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": e.code, "message": e.message, "data": e.data}}
    except Exception as e:  # noqa: BLE001
        log.exception("Payme xatosi")
        last_error = str(e)
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32400, "message": {"uz": "Tizim xatosi", "ru": "Системная ошибка", "en": "System error"}}}


async def _order_from_account(params: dict) -> Payment:
    field = await account_field()
    raw = (params.get("account") or {}).get(field)
    try:
        oid = int(str(raw))
    except (TypeError, ValueError):
        raise PaymeError(-31050, "Buyurtma topilmadi", "Заказ не найден", "Order not found", field)
    async with session_scope() as s:
        p = await s.get(Payment, oid)
    if not p:
        raise PaymeError(-31050, "Buyurtma topilmadi", "Заказ не найден", "Order not found", field)
    return p


def _check_amount(p: Payment, params: dict) -> None:
    if int(params.get("amount") or -1) != p.amount * 100:
        raise PaymeError(-31001, "Noto'g'ri summa", "Неверная сумма", "Incorrect amount")


async def _receipt(p: Payment) -> dict | None:
    ikpu = (await settings.get("payme_ikpu") or "").strip()
    if not ikpu:
        return None
    return {"receipt_type": 0, "items": [{
        "title": p.title[:128], "price": p.amount * 100, "count": 1, "code": ikpu,
        "package_code": (await settings.get("payme_package_code") or "").strip(),
        "vat_percent": int(await settings.get("payme_vat_percent") or 0),
    }]}


async def check_perform(params: dict) -> dict:
    p = await _order_from_account(params)
    if p.state != 0:
        raise PaymeError(-31051, "Buyurtma allaqachon to'langan yoki bekor qilingan", "Заказ уже оплачен или отменён",
                         "Order is not available", await account_field())
    _check_amount(p, params)
    res: dict[str, Any] = {"allow": True}
    detail = await _receipt(p)
    if detail:
        res["detail"] = detail
    return res


async def _by_payme_id(tid: str) -> Payment | None:
    async with session_scope() as s:
        return (await s.execute(select(Payment).where(Payment.payme_id == tid))).scalars().first()


async def _cancel(p: Payment, reason: int) -> Payment:
    """state 1 → -1 (to'lovdan oldin), state 2 → -2 (to'lovdan keyin, pul qaytarilgan)."""
    refund = False
    async with session_scope() as s:
        obj = await s.get(Payment, p.id)
        if obj.state == 1:
            obj.state = -1
        elif obj.state == 2:
            obj.state = -2
            refund = True
        else:
            return obj
        obj.cancel_time = now_ms()
        obj.reason = reason
        obj.cancelled_at = utcnow()
    async with session_scope() as s:
        obj = await s.get(Payment, p.id)
    if refund:
        from . import subscriptions

        await subscriptions.refund_payment(obj)
    await hub.emit("payment", {"id": obj.id, "state": obj.state})
    return obj


async def create_transaction(params: dict) -> dict:
    tid = str(params.get("id") or "")
    existing = await _by_payme_id(tid)
    if existing:
        if existing.state != 1:
            raise PaymeError(-31008, "Operatsiyani bajarib bo'lmaydi", "Невозможно выполнить операцию", "Unable to perform operation")
        if now_ms() - (existing.create_time or 0) > TIMEOUT_MS:
            await _cancel(existing, 4)
            raise PaymeError(-31008, "Tranzaksiya muddati o'tgan", "Истёк срок транзакции", "Transaction timed out")
        return {"create_time": existing.create_time, "transaction": str(existing.id), "state": existing.state}
    p = await _order_from_account(params)
    if p.state == 1 and p.payme_id and p.payme_id != tid:
        raise PaymeError(-31050, "Buyurtma boshqa tranzaksiya bilan band", "Заказ ожидает оплаты другой транзакцией",
                         "Order is busy", await account_field())
    if p.state != 0:
        raise PaymeError(-31051, "Buyurtma allaqachon to'langan yoki bekor qilingan", "Заказ уже оплачен или отменён",
                         "Order is not available", await account_field())
    _check_amount(p, params)
    async with session_scope() as s:
        obj = await s.get(Payment, p.id)
        obj.payme_id = tid
        obj.payme_time = int(params.get("time") or now_ms())
        obj.create_time = now_ms()
        obj.state = 1
        create_time, pid = obj.create_time, obj.id
    await hub.emit("payment", {"id": pid, "state": 1})
    return {"create_time": create_time, "transaction": str(pid), "state": 1}


async def perform_transaction(params: dict) -> dict:
    p = await _by_payme_id(str(params.get("id") or ""))
    if not p:
        raise PaymeError(-31003, "Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found")
    if p.state == 2:
        return {"transaction": str(p.id), "perform_time": p.perform_time, "state": 2}
    if p.state != 1:
        raise PaymeError(-31008, "Operatsiyani bajarib bo'lmaydi", "Невозможно выполнить операцию", "Unable to perform operation")
    if now_ms() - (p.create_time or 0) > TIMEOUT_MS:
        await _cancel(p, 4)
        raise PaymeError(-31008, "Tranzaksiya muddati o'tgan", "Истёк срок транзакции", "Transaction timed out")
    async with session_scope() as s:
        obj = await s.get(Payment, p.id)
        obj.state = 2
        obj.perform_time = now_ms()
        obj.paid_at = utcnow()
        perform_time = obj.perform_time
    await _on_paid(p.id)
    return {"transaction": str(p.id), "perform_time": perform_time, "state": 2}


async def _on_paid(payment_id: int) -> None:
    from . import subscriptions

    async with session_scope() as s:
        p = await s.get(Payment, payment_id)
    try:
        await subscriptions.extend(p.tg_id, p.days, kind="payme", payment_id=p.id, note=f"{p.amount} so'm")
        await subscriptions.send_access(p.tg_id, "paid_ok")
    except Exception:  # noqa: BLE001
        log.exception("To'lovdan keyin obunani faollashtirishda xato")
    await hub.emit("payment", {"id": p.id, "state": 2})
    await hub.emit("alert", {"level": "success", "text": f"💳 Yangi to'lov: {p.amount:,} so'm — {p.title}".replace(",", " ")})
    who = html.escape(p.lead.display if p.lead else str(p.tg_id))
    await telegram_staff(f"💳 <b>Yangi to'lov!</b>\n👤 {who}\n📦 {html.escape(p.title)}\n💰 {p.amount:,} so'm".replace(",", " "),
                         admins=True, path="/payments")


async def cancel_transaction(params: dict) -> dict:
    p = await _by_payme_id(str(params.get("id") or ""))
    if not p:
        raise PaymeError(-31003, "Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found")
    if p.state in (1, 2):
        p = await _cancel(p, int(params.get("reason") or 0))
    return {"transaction": str(p.id), "cancel_time": p.cancel_time, "state": p.state}


async def check_transaction(params: dict) -> dict:
    p = await _by_payme_id(str(params.get("id") or ""))
    if not p:
        raise PaymeError(-31003, "Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found")
    return {"create_time": p.create_time or 0, "perform_time": p.perform_time or 0, "cancel_time": p.cancel_time or 0,
            "transaction": str(p.id), "state": p.state, "reason": p.reason}


async def get_statement(params: dict) -> dict:
    frm, to = int(params.get("from") or 0), int(params.get("to") or 0)
    field = await account_field()
    async with session_scope() as s:
        rows = (await s.execute(select(Payment).where(Payment.payme_id.is_not(None), Payment.payme_time >= frm,
                                                      Payment.payme_time <= to).order_by(Payment.payme_time))).scalars().all()
    return {"transactions": [{
        "id": p.payme_id, "time": p.payme_time, "amount": p.amount * 100, "account": {field: str(p.id)},
        "create_time": p.create_time or 0, "perform_time": p.perform_time or 0, "cancel_time": p.cancel_time or 0,
        "transaction": str(p.id), "state": p.state, "reason": p.reason,
    } for p in rows]}


async def set_fiscal_data(params: dict) -> dict:
    p = await _by_payme_id(str(params.get("id") or ""))
    if not p:
        raise PaymeError(-31003, "Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found")
    async with session_scope() as s:
        obj = await s.get(Payment, p.id)
        data = dict(obj.fiscal or {})
        data[str(params.get("type") or "PERFORM")] = params.get("fiscal_data")
        obj.fiscal = data
    return {"success": True}


METHODS = {
    "CheckPerformTransaction": check_perform,
    "CreateTransaction": create_transaction,
    "PerformTransaction": perform_transaction,
    "CancelTransaction": cancel_transaction,
    "CheckTransaction": check_transaction,
    "GetStatement": get_statement,
    "SetFiscalData": set_fiscal_data,
}
