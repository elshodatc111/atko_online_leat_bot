"""Ma'lumotlar bazasi jadvallari."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

# ---------------------------------------------------------------- konstantalar

LEAD_STATUSES: dict[str, str] = {
    "new": "🆕 Yangi",
    "contacted": "📞 Aloqada",
    "thinking": "🤔 O'ylab ko'radi",
    "trial": "📝 Kursga yozilmoqchi",
    "accepted": "✅ Kursga qabul qilindi",
    "rejected": "❌ Rad etdi",
}

REJECT_REASONS: list[str] = [
    "Narx qimmat",
    "Vaqt to'g'ri kelmadi",
    "Boshqa markazni tanladi",
    "Qiziqmay qoldi",
    "Aloqaga chiqmadi",
    "Boshqa",
]

GOALS: dict[str, dict[str, str]] = {
    "topik": {"uz": "🎯 TOPIK"},
    "eps": {"uz": "💼 EPS-TOPIK (ish)"},
    "speaking": {"uz": "🗣 Noldan so'zlashuv"},
    "other": {"uz": "✨ Boshqa"},
}

FORMATS: dict[str, dict[str, str]] = {
    "online": {"uz": "💻 Online"},
    "offline": {"uz": "🏫 Offline"},
    "hybrid": {"uz": "🔄 Gibrid"},
}

TEMPERATURES = {"hot": "🔥 Issiq", "warm": "🌤 Iliq", "cold": "❄️ Sovuq"}

CHAT_STATUSES = {"waiting": "⏳ Kutmoqda", "active": "💬 Faol", "closed": "🔒 Yopilgan"}


# ---------------------------------------------------------------- jadvallar


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Staff(Base):
    """Admin va operatorlar."""

    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    tg_username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128))  # leadga ko'rinadigan ism
    role: Mapped[str] = mapped_column(String(16), default="operator")  # admin / operator
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    invite_expires: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class LoginToken(Base):
    __tablename__ = "login_tokens"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/confirmed/used
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    tg_username: Mapped[str | None] = mapped_column(String(64))
    tg_name: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    lang: Mapped[str] = mapped_column(String(4), default="uz")
    goal: Mapped[str | None] = mapped_column(String(32))
    study_format: Mapped[str | None] = mapped_column(String(32))
    level: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(64))
    interested_tariff: Mapped[str | None] = mapped_column(String(128))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255))
    temperature: Mapped[str | None] = mapped_column(String(8))
    ai_summary: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16), default="consultant")  # consultant / tutor
    onboarding_step: Mapped[str | None] = mapped_column(String(16))  # lang/name/phone/goal/format/None
    trial_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # botni bloklagan
    reminders_stopped: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_by_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_operator_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    tutor_day: Mapped[date | None] = mapped_column(Date)
    tutor_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_input: Mapped[str | None] = mapped_column(String(32))  # rating_comment va h.k.
    pending_ref: Mapped[int | None] = mapped_column(Integer)
    quiz_state: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    source: Mapped[Source | None] = relationship(lazy="joined")
    accepted_by: Mapped[Staff | None] = relationship(foreign_keys=[accepted_by_id], lazy="joined")
    last_operator: Mapped[Staff | None] = relationship(foreign_keys=[last_operator_id], lazy="joined")

    @property
    def display(self) -> str:
        return self.name or self.tg_name or (f"@{self.tg_username}" if self.tg_username else f"#{self.tg_id}")

    @property
    def status_label(self) -> str:
        return LEAD_STATUSES.get(self.status, self.status)


class Chat(Base):
    """Lead va operator o'rtasidagi suhbat sessiyasi."""

    __tablename__ = "chats"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="waiting", index=True)
    reason: Mapped[str] = mapped_column(String(32), default="user")  # user / ai / complaint / trial
    off_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    sla_start: Mapped[datetime] = mapped_column(DateTime, default=utcnow)  # kutish hisobi boshlanishi
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    last_lead_msg_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_operator_msg_at: Mapped[datetime | None] = mapped_column(DateTime)
    sla_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    idle_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[int | None] = mapped_column(Integer)
    rating_comment: Mapped[str | None] = mapped_column(Text)
    transfers: Mapped[int] = mapped_column(Integer, default=0)
    unread: Mapped[int] = mapped_column(Integer, default=0)

    lead: Mapped[Lead] = relationship(lazy="joined")
    operator: Mapped[Staff | None] = relationship(foreign_keys=[operator_id], lazy="joined")

    @property
    def status_label(self) -> str:
        return CHAT_STATUSES.get(self.status, self.status)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), index=True)
    sender: Mapped[str] = mapped_column(String(16))  # lead / ai / operator / system / bot
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    mode: Mapped[str | None] = mapped_column(String(16))  # consultant / tutor
    kind: Mapped[str] = mapped_column(String(16), default="text")  # text/photo/voice/audio/video/document/video_note/sticker
    text: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(512))
    file_name: Mapped[str | None] = mapped_column(String(255))
    mime: Mapped[str | None] = mapped_column(String(128))
    file_size: Mapped[int | None] = mapped_column(Integer)
    transcript: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    staff: Mapped[Staff | None] = relationship(lazy="joined")


class LeadComment(Base):
    __tablename__ = "lead_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    staff: Mapped[Staff | None] = relationship(lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    staff: Mapped[Staff | None] = relationship(lazy="joined")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class Holiday(Base):
    __tablename__ = "holidays"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(128))


class Tariff(Base):
    __tablename__ = "tariffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), default="group")  # group / individual / hybrid
    price: Mapped[int] = mapped_column(Integer, default=0)  # so'm (obuna bo'lmagan tariflar uchun)
    price_period: Mapped[str] = mapped_column(String(32), default="oyiga")
    is_subscription: Mapped[bool] = mapped_column(Boolean, default=False)  # Payme orqali obuna (yopiq guruh)
    name_uz: Mapped[str] = mapped_column(String(128))
    name_ru: Mapped[str] = mapped_column(String(128), default="")  # eski ustun (bot faqat o'zbekcha)
    desc_uz: Mapped[str] = mapped_column(Text)
    desc_ru: Mapped[str] = mapped_column(Text, default="")  # eski ustun (bot faqat o'zbekcha)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReminderStep(Base):
    __tablename__ = "reminder_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    day_offset: Mapped[int] = mapped_column(Integer)
    text_uz: Mapped[str] = mapped_column(Text)
    text_ru: Mapped[str] = mapped_column(Text, default="")  # eski ustun (bot faqat o'zbekcha)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReminderLog(Base):
    __tablename__ = "reminder_log"
    __table_args__ = (UniqueConstraint("lead_id", "step_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("reminder_steps.id", ondelete="CASCADE"))
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Broadcast(Base):
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    segment: Mapped[str] = mapped_column(String(16))  # all / accepted / not_accepted
    kind: Mapped[str] = mapped_column(String(16))  # text / photo / video
    text: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft/running/done/cancelled
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_by: Mapped[Staff | None] = relationship(lazy="joined")


class AiUsage(Base):
    __tablename__ = "ai_usage"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    audio_seconds: Mapped[float] = mapped_column(Float, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)


class SubscriptionPlan(Base):
    """Obuna tarifining muddatli variantlari (1 oy / 3 oy / 12 oy)."""

    __tablename__ = "subscription_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id", ondelete="CASCADE"), index=True)
    title_uz: Mapped[str] = mapped_column(String(64))
    title_ru: Mapped[str] = mapped_column(String(64), default="")  # eski ustun (bot faqat o'zbekcha)
    days: Mapped[int] = mapped_column(Integer, default=30)
    price: Mapped[int] = mapped_column(Integer, default=0)  # so'm
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    tariff: Mapped[Tariff] = relationship(lazy="joined")


PAYMENT_STATES = {0: "🆕 Yaratildi", 1: "⏳ To'lov jarayonida", 2: "✅ To'landi", -1: "✖️ Bekor qilindi", -2: "↩️ Qaytarildi"}


class Payment(Base):
    """Payme orqali to'lov (buyurtma + Payme tranzaksiyasi)."""

    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("subscription_plans.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    days: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)  # so'm
    state: Mapped[int] = mapped_column(Integer, default=0, index=True)
    payme_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    payme_time: Mapped[int | None] = mapped_column(BigInteger)  # Payme yuborgan time (ms)
    create_time: Mapped[int | None] = mapped_column(BigInteger)  # ms
    perform_time: Mapped[int | None] = mapped_column(BigInteger)
    cancel_time: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[int | None] = mapped_column(Integer)
    fiscal: Mapped[dict | None] = mapped_column(JSON)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)  # "to'lov yakunlanmadi" eslatmasi
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)

    lead: Mapped[Lead | None] = relationship(lazy="joined")

    @property
    def state_label(self) -> str:
        return PAYMENT_STATES.get(self.state, str(self.state))


class Subscription(Base):
    """Yopiq Telegram guruhga kirish huquqi (bitta Telegram akkaunt — bitta yozuv)."""

    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    name: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    whitelisted: Mapped[bool] = mapped_column(Boolean, default=False)  # muddatsiz ruxsat
    in_group: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_link: Mapped[str | None] = mapped_column(String(255))
    reminded_3: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_1: Mapped[bool] = mapped_column(Boolean, default=False)
    expired_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    lead: Mapped[Lead | None] = relationship(lazy="joined")

    @property
    def is_active(self) -> bool:
        return self.whitelisted or self.expires_at > utcnow()

    @property
    def days_left(self) -> int:
        sec = (self.expires_at - utcnow()).total_seconds()
        return max(0, int((sec + 86399) // 86400))


class SubscriptionEvent(Base):
    __tablename__ = "subscription_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # payme / manual / set_date / refund / revoke / removed / joined / link
    days: Mapped[int | None] = mapped_column(Integer)
    payment_id: Mapped[int | None] = mapped_column(Integer)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    staff: Mapped[Staff | None] = relationship(lazy="joined")


class LoginCode(Base):
    """Panelga kirish uchun Telegramga yuboriladigan bir martalik kod."""

    __tablename__ = "login_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ================================================================ v3: kurs paketlari, kanal, o'quv guruhlari


class TariffOption(Base):
    """Kurs tariflarining paket variantlari (12 dars / 20 dars). To'lov admin orqali (Payme emas)."""

    __tablename__ = "tariff_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id", ondelete="CASCADE"), index=True)
    lessons: Mapped[int] = mapped_column(Integer, default=12)
    per_week: Mapped[int] = mapped_column(Integer, default=3)
    months: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[int] = mapped_column(Integer, default=0)  # so'm
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tariff: Mapped[Tariff] = relationship(lazy="joined")
