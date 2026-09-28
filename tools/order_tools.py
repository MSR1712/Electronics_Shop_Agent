"""
Order management tools.

SECURITY: customer_id and conversation_id are NEVER LLM-supplied
arguments. Each tool is built by make_order_tools(customer_id,
conversation_id), which closes over both — the LLM's tool-call arguments
literally cannot name a different customer or conversation, because those
parameters don't exist in the tools' schemas.

CONFIRMATION WORKFLOW (Change 1): the LLM can never create an order
directly. prepare_order() only ever produces a PendingConfirmation row —
inert, no inventory touched. confirm_order() is the only path to an actual
Order, and it re-verifies, at the database level, that:
  1. the confirmation exists,
  2. belongs to this customer,
  3. belongs to this conversation,
  4. is still PENDING (not already consumed/expired/superseded),
  5. has not expired,
before doing anything. The PENDING -> CONSUMED transition itself is an
atomic conditional UPDATE, so two simultaneous confirm attempts (or a
replay) can only ever succeed once — see tests/test_confirmation.py.

ATOMICITY (Change 3 covers cancellation similarly): inventory decrement on
purchase, and the order status transition on cancellation, are each a
single conditional UPDATE ... WHERE ... checked by rowcount, never a
read-then-write, so concurrent requests can't double-spend stock or
double-restore it.

MONEY: everything is integer cents end-to-end; price is always read from
the inventory table at prepare_order time and snapshotted onto the
confirmation and the resulting order — never accepted from the LLM.
"""

import json
from datetime import timedelta
from decimal import Decimal

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import update

from config import settings
from db.models import (
    CANCELLABLE_ORDER_STATUSES,
    InventoryItem,
    Order,
    OrderItem,
    OrderStatus,
    PendingConfirmation,
    PendingConfirmationStatus,
    utcnow,
)
from db.session import get_session


class OrderItemInput(BaseModel):
    sku: str = Field(description="Product SKU to order")
    quantity: int = Field(description="Quantity to order", gt=0)


def _usd(cents: int) -> str:
    return f"${Decimal(cents) / 100:.2f}"


def make_order_tools(customer_id: str, conversation_id: str):
    """
    Returns [prepare_order, confirm_order, get_order_status, cancel_order,
    list_orders] bound to (customer_id, conversation_id). Call this fresh
    per conversation turn with the session's authenticated identity — never
    expose either as a tool parameter the model can set.
    """

    @tool
    def prepare_order(items: list[OrderItemInput]) -> str:
        """
        Prepares a proposed order for the customer to confirm. Resolves
        SKUs and current prices from the catalog and returns a
        confirmation_id and total — this does NOT create an order or
        touch inventory. You must NOT call confirm_order until the
        customer has clearly and explicitly agreed to this exact proposal
        (e.g. "yes", "confirm it", "place the order") — a question like
        "how much would that be" is not confirmation.
        """
        with get_session() as session:
            resolved = []
            errors = []
            for item in items:
                inv = session.get(InventoryItem, item.sku)
                if inv is None:
                    errors.append({"sku": item.sku, "error": "SKU not found"})
                    continue
                if inv.stock_level < item.quantity:
                    errors.append(
                        {
                            "sku": item.sku,
                            "name": inv.name,
                            "error": f"only {inv.stock_level} in stock, requested {item.quantity}",
                        }
                    )
                    continue
                resolved.append(
                    {
                        "sku": inv.sku,
                        "name": inv.name,
                        "quantity": item.quantity,
                        "unit_price_cents": inv.price_cents,
                    }
                )

            if errors:
                return json.dumps({"success": False, "errors": errors})

            total_cents = sum(r["quantity"] * r["unit_price_cents"] for r in resolved)
            now = utcnow()
            expires_at = now + timedelta(minutes=settings.confirmation_ttl_minutes)

            # A fresh proposal supersedes any prior open one for this
            # customer+conversation, so an old confirmation_id can never
            # be confirmed after the customer changed their mind/quantity.
            session.execute(
                update(PendingConfirmation)
                .where(
                    PendingConfirmation.customer_id == customer_id,
                    PendingConfirmation.conversation_id == conversation_id,
                    PendingConfirmation.status == PendingConfirmationStatus.PENDING,
                )
                .values(status=PendingConfirmationStatus.SUPERSEDED)
            )

            pending = PendingConfirmation(
                customer_id=customer_id,
                conversation_id=conversation_id,
                items_json=json.dumps(resolved),
                total_cents=total_cents,
                status=PendingConfirmationStatus.PENDING,
                created_at=now,
                expires_at=expires_at,
            )
            session.add(pending)
            session.commit()
            session.refresh(pending)

            return json.dumps(
                {
                    "success": True,
                    "confirmation_id": pending.id,
                    "items": resolved,
                    "total_cents": total_cents,
                    "total_display": _usd(total_cents),
                    "expires_at": expires_at.isoformat(),
                    "note": "Not yet ordered. Call confirm_order with this confirmation_id "
                    "only once the customer explicitly confirms.",
                }
            )

    @tool
    def confirm_order(confirmation_id: int) -> str:
        """
        Executes the purchase for a previously prepared order, ONLY after
        the customer has explicitly confirmed it in this same
        conversation. Call this with the confirmation_id returned by
        prepare_order — never invent one, and never call this without a
        clear, explicit "yes"/"confirm"/"go ahead" from the customer.
        """
        with get_session() as session:
            now = utcnow()

            # Atomic: PENDING -> CONSUMED only succeeds if every ownership
            # and freshness check holds, evaluated by the DB in one
            # conditional UPDATE. Two simultaneous confirm_order calls (or
            # a replay of the same confirmation_id) can flip this exactly
            # once — see test_confirmation.py's replay/concurrency tests.
            result = session.execute(
                update(PendingConfirmation)
                .where(
                    PendingConfirmation.id == confirmation_id,
                    PendingConfirmation.customer_id == customer_id,
                    PendingConfirmation.conversation_id == conversation_id,
                    PendingConfirmation.status == PendingConfirmationStatus.PENDING,
                    PendingConfirmation.expires_at > now,
                )
                .values(status=PendingConfirmationStatus.CONSUMED)
            )

            if result.rowcount == 0:
                # Diagnose without leaking another customer's confirmation.
                existing = session.get(PendingConfirmation, confirmation_id)
                if existing is None or existing.customer_id != customer_id or existing.conversation_id != conversation_id:
                    return json.dumps({"success": False, "error": "No matching pending confirmation found."})
                if existing.status != PendingConfirmationStatus.PENDING:
                    return json.dumps(
                        {"success": False, "error": f"That confirmation is no longer pending (status: {existing.status.value})."}
                    )
                if existing.expires_at <= now:
                    return json.dumps({"success": False, "error": "That confirmation has expired. Please request the order again."})
                return json.dumps({"success": False, "error": "Confirmation could not be applied."})

            pending = session.get(PendingConfirmation, confirmation_id)
            items = json.loads(pending.items_json)

            order = Order(customer_id=customer_id, status=OrderStatus.CONFIRMED)
            session.add(order)
            session.flush()

            stock_errors = []
            line_items = []
            for entry in items:
                res = session.execute(
                    update(InventoryItem)
                    .where(InventoryItem.sku == entry["sku"], InventoryItem.stock_level >= entry["quantity"])
                    .values(stock_level=InventoryItem.stock_level - entry["quantity"])
                )
                if res.rowcount == 0:
                    stock_errors.append({"sku": entry["sku"], "name": entry["name"], "error": "insufficient stock"})
                    continue
                session.add(
                    OrderItem(
                        order_id=order.id,
                        sku=entry["sku"],
                        quantity=entry["quantity"],
                        unit_price_cents=entry["unit_price_cents"],
                    )
                )
                line_items.append(entry)

            if stock_errors:
                # Rolls back the order AND reverts the confirmation back to
                # PENDING (same uncommitted transaction) — stock genuinely
                # changed between prepare and confirm; let the customer
                # retry rather than silently failing a "consumed" confirmation.
                session.rollback()
                return json.dumps(
                    {
                        "success": False,
                        "error": "Stock changed since this order was prepared.",
                        "details": stock_errors,
                    }
                )

            session.commit()
            session.refresh(order)

            return json.dumps(
                {
                    "success": True,
                    "order_id": order.id,
                    "status": order.status.value,
                    "items": line_items,
                    "total_cents": order.total_cents,
                    "total_display": _usd(order.total_cents),
                }
            )

    @tool
    def get_order_status(order_id: int) -> str:
        """
        Looks up the status and contents of an order by its numeric ID,
        for the current authenticated customer only. Returns the same
        "not found" for a nonexistent order and for another customer's
        order — never confirms another customer's order exists.

        Once an order has shipped, the response includes tracking_number
        and carrier — share those with the customer verbatim if they ask
        to track their order. tracking_number/carrier/shipped_at/
        delivered_at are null until the order actually reaches that
        stage — never state a tracking number or delivery status that
        isn't present in this response.
        """
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == order_id, Order.customer_id == customer_id)
                .first()
            )
            if order is None:
                return json.dumps({"success": False, "error": "Order not found."})

            items = [
                {"sku": item.sku, "quantity": item.quantity, "unit_price_cents": item.unit_price_cents}
                for item in order.items
            ]
            return json.dumps(
                {
                    "success": True,
                    "order_id": order.id,
                    "status": order.status.value,
                    "created_at": order.created_at.isoformat(),
                    "items": items,
                    "total_cents": order.total_cents,
                    "total_display": _usd(order.total_cents),
                    "tracking_number": order.tracking_number,
                    "carrier": order.carrier,
                    "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
                    "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
                }
            )

    @tool
    def list_orders() -> str:
        """
        Lists all past orders for the current authenticated customer, most
        recent first, with each order's id, status, item count, and total.
        Use this when the customer asks how many orders they've placed,
        wants their order history, or doesn't remember an order ID —
        follow up with get_order_status on a specific order_id from this
        list if they want full line-item detail.
        """
        with get_session() as session:
            orders = (
                session.query(Order)
                .filter(Order.customer_id == customer_id)
                .order_by(Order.created_at.desc())
                .all()
            )
            results = [
                {
                    "order_id": o.id,
                    "status": o.status.value,
                    "created_at": o.created_at.isoformat(),
                    "item_count": len(o.items),
                    "total_cents": o.total_cents,
                    "total_display": _usd(o.total_cents),
                    "tracking_number": o.tracking_number,
                }
                for o in orders
            ]
            return json.dumps({"success": True, "count": len(results), "orders": results})

    @tool
    def cancel_order(order_id: int) -> str:
        """
        Cancels an order for the current authenticated customer, if it's
        still pending/confirmed (not yet shipped). Restores the cancelled
        quantities to inventory.
        """
        with get_session() as session:
            # Atomic conditional status transition: only flips to CANCELLED
            # if the order is owned by this customer AND currently in a
            # cancellable status. rowcount tells us definitively whether
            # THIS call performed the transition — a second, concurrent
            # cancel of the same order will see rowcount 0 and therefore
            # never restore inventory a second time.
            result = session.execute(
                update(Order)
                .where(
                    Order.id == order_id,
                    Order.customer_id == customer_id,
                    Order.status.in_(CANCELLABLE_ORDER_STATUSES),
                )
                .values(status=OrderStatus.CANCELLED)
            )

            if result.rowcount == 0:
                existing = session.query(Order).filter(Order.id == order_id, Order.customer_id == customer_id).first()
                if existing is None:
                    return json.dumps({"success": False, "error": "Order not found."})
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Order is '{existing.status.value}' and can no longer be cancelled.",
                    }
                )

            order = session.get(Order, order_id)
            try:
                for item in order.items:
                    session.execute(
                        update(InventoryItem)
                        .where(InventoryItem.sku == item.sku)
                        .values(stock_level=InventoryItem.stock_level + item.quantity)
                    )
            except Exception:
                # Inventory restoration failed — roll back the status
                # transition too, so the order isn't left cancelled with
                # stock never returned.
                session.rollback()
                return json.dumps({"success": False, "error": "Cancellation failed while restoring inventory; no changes were made."})

            session.commit()
            return json.dumps({"success": True, "order_id": order.id, "status": "cancelled"})

    return [prepare_order, confirm_order, get_order_status, cancel_order, list_orders]
