"""
SQLAlchemy models for the transactional side of the shop: customers,
inventory, orders, order items, pending order confirmations, returns, and
escalations.

Money is stored as integer cents (never float) — see *_cents columns and
the `*_usd` properties, which convert to Decimal only for display.
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    # Naive UTC, deliberately — SQLite (this project's default DB) does not
    # preserve tzinfo across a round-trip, so a value read back from the DB
    # would be naive while a freshly-constructed aware datetime wouldn't be,
    # and comparing the two raises TypeError. Every datetime in this schema
    # is UTC by convention; keep them all naive for consistent comparisons
    # (see tools/order_tools.py's expiry check, which hit exactly this bug).
    return datetime.utcnow()


def cents_to_usd(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURN_REQUESTED = "return_requested"
    REFUNDED = "refunded"


# Orders in these statuses may still be cancelled directly by the customer.
CANCELLABLE_ORDER_STATUSES = [OrderStatus.PENDING, OrderStatus.CONFIRMED]

# Orders in these statuses may have a return requested against them.
RETURNABLE_ORDER_STATUSES = [
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
]


class PendingConfirmationStatus(str, enum.Enum):
    PENDING = "pending"
    CONSUMED = "consumed"       # successfully turned into an order
    EXPIRED = "expired"
    SUPERSEDED = "superseded"   # replaced by a newer prepare_order call


class ReturnStatus(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECEIVED = "received"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class EscalationStatus(str, enum.Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    WAITING_FOR_AGENT = "waiting_for_agent"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Customer(Base):
    """
    interfaces/chat_app.py's sidebar picker and api/routers/customers.py's
    demo POST /api/session still log in by bare customer_id, with no
    password check, for quick testing — real customers created through
    api/routers/auth.py's signup/login have a password_hash and must
    authenticate with it (see api/passwords.py for the hashing scheme).
    Never store or log a plaintext password.
    """

    __tablename__ = "customers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    # Nullable: the seeded demo customers (cust-001, ...) have none and can
    # only be logged into via the bare-customer_id demo picker, not
    # api/routers/auth.py's password login.
    password_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class InventoryItem(Base):
    """
    Authoritative source of truth for stock counts and price. Product
    *descriptions* for semantic search live in Chroma (see rag/), but
    Chroma is a retrieval index over this table's identity (SKU), never a
    second source of truth for price or stock — see tools/product_tools.py.
    """

    __tablename__ = "inventory"

    sku = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    price_cents = Column(Integer, nullable=False)
    stock_level = Column(Integer, nullable=False, default=0)

    __table_args__ = (CheckConstraint("stock_level >= 0", name="stock_non_negative"),)

    order_items = relationship("OrderItem", back_populates="inventory_item")

    @property
    def price_usd(self) -> Decimal:
        return cents_to_usd(self.price_cents)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    status = Column(SAEnum(OrderStatus), nullable=False, default=OrderStatus.CONFIRMED)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Shipment tracking — set only by tools/fulfillment_tools.py's admin-only
    # mark_shipped/mark_delivered (never by the customer-facing agent tools
    # in tools/order_tools.py, same "LLM never fabricates state" principle
    # as the confirmation/return workflows). All nullable: unset until the
    # order actually reaches that stage.
    tracking_number = Column(String, nullable=True)
    carrier = Column(String, nullable=True)
    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    returns = relationship("Return", back_populates="order")

    @property
    def total_cents(self) -> int:
        return sum(item.quantity * item.unit_price_cents for item in self.items)

    @property
    def total_usd(self) -> Decimal:
        return cents_to_usd(self.total_cents)


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sku = Column(String, ForeignKey("inventory.sku"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price_cents = Column(Integer, nullable=False)  # snapshot at order time

    order = relationship("Order", back_populates="items")
    inventory_item = relationship("InventoryItem", back_populates="order_items")

    @property
    def unit_price_usd(self) -> Decimal:
        return cents_to_usd(self.unit_price_cents)


class PendingConfirmation(Base):
    """
    Backend-owned "did the customer actually agree to this transaction"
    state. The LLM can prepare one (prepare_order) but cannot authorize
    the resulting purchase — only confirm_order, gated by the checks in
    tools/order_tools.py, can turn this into a real Order. See
    tests/test_confirmation.py for the guarantees this enforces.

    `items_json` is a JSON-encoded snapshot of [{sku, name, quantity,
    unit_price_cents}], captured at prepare time so confirm_order never
    needs to trust the LLM to restate the order accurately.
    """

    __tablename__ = "pending_confirmations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    conversation_id = Column(String, nullable=False, index=True)
    items_json = Column(Text, nullable=False)
    total_cents = Column(Integer, nullable=False)
    status = Column(
        SAEnum(PendingConfirmationStatus),
        nullable=False,
        default=PendingConfirmationStatus.PENDING,
    )
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)


class Return(Base):
    """
    Return/refund workflow state. request_return() (customer-facing, via
    order_agent) only ever creates a REQUESTED row — it cannot approve or
    refund itself. approve_return/reject_return/process_refund are
    deliberately NOT exposed as agent tools; they represent an internal
    admin/back-office action (see tools/return_tools.py docstring).
    """

    __tablename__ = "returns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    status = Column(SAEnum(ReturnStatus), nullable=False, default=ReturnStatus.REQUESTED)
    # Snapshot of the order's status before the return was requested, so a
    # rejected/cancelled return can restore it rather than guessing.
    pre_return_order_status = Column(SAEnum(OrderStatus), nullable=False)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    order = relationship("Order", back_populates="returns")


class Escalation(Base):
    __tablename__ = "escalations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    conversation_id = Column(String, nullable=True, index=True)
    reason = Column(Text, nullable=False)
    status = Column(SAEnum(EscalationStatus), nullable=False, default=EscalationStatus.OPEN)
    assigned_agent = Column(String, nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
