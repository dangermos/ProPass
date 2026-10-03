"""Persistence for canonical merchandise, versioned carts and immutable receipts."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class CheckoutSession(Base):
    __tablename__ = "checkout_session"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(80))
    run_id: Mapped[str] = mapped_column(String(36), unique=True)
    scenario: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Cart(Base):
    __tablename__ = "cart"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("checkout_session.id"), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    prepared_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prepared_frame_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prepared_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class PhysicalItem(Base):
    __tablename__ = "physical_item"
    __table_args__ = (UniqueConstraint("session_id", "object_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("checkout_session.id"))
    object_id: Mapped[str] = mapped_column(String(100))
    sku: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class CheckoutEvent(Base):
    __tablename__ = "checkout_event"
    __table_args__ = (UniqueConstraint("run_id", "event_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("checkout_session.id"))
    run_id: Mapped[str] = mapped_column(String(36))
    event_id: Mapped[str] = mapped_column(String(180))
    event_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(40), nullable=True)
    timestamp: Mapped[float] = mapped_column(Float)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Receipt(Base):
    __tablename__ = "receipt"
    __table_args__ = (UniqueConstraint("cart_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("cart.id"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    confirmed_version: Mapped[int] = mapped_column(Integer)
    customer_name: Mapped[str] = mapped_column(String(80))
    lines: Mapped[list] = mapped_column(JSON)
    total: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
