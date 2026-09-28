"""
Order fulfillment / shipment-tracking workflow.

No customer-facing tools here — this whole module is internal/admin
operations (NOT decorated as agent tools, NOT wired into any LangGraph
node), same as tools/return_tools.py's approve_return/reject_return/
process_refund. A customer's order status only ever moves forward
(confirmed -> processing -> shipped -> delivered) through a human/admin
action taken here — never because the LLM decided to say so. The
customer-facing read path is get_order_status/list_orders in
tools/order_tools.py, which surface tracking_number/carrier/shipped_at/
delivered_at once these have set them.

In a real deployment these would be called from a warehouse/fulfillment
system's webhook or an internal admin tool; for this demo, call them from
scripts/ship_order.py. Each is an atomic conditional transition, same
pattern as order confirmation/cancellation and the return workflow, so
concurrent/duplicate calls can't apply the same transition twice.
"""

from db.models import Order, OrderStatus, utcnow
from db.session import get_session
from sqlalchemy import update


def mark_processing(order_id: int) -> dict:
    with get_session() as session:
        result = session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.CONFIRMED)
            .values(status=OrderStatus.PROCESSING)
        )
        if result.rowcount == 0:
            existing = session.get(Order, order_id)
            if existing is None:
                return {"success": False, "error": "Order not found."}
            return {
                "success": False,
                "error": f"Order must be 'confirmed' to start processing (current status: {existing.status.value}).",
            }
        session.commit()
        return {"success": True, "order_id": order_id, "status": OrderStatus.PROCESSING.value}


def mark_shipped(order_id: int, tracking_number: str, carrier: str | None = None) -> dict:
    """Confirmed or processing -> shipped. Either prior status is accepted
    so a demo/admin can ship directly without a separate "start processing"
    step first."""
    with get_session() as session:
        result = session.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.PROCESSING]),
            )
            .values(
                status=OrderStatus.SHIPPED,
                tracking_number=tracking_number,
                carrier=carrier,
                shipped_at=utcnow(),
            )
        )
        if result.rowcount == 0:
            existing = session.get(Order, order_id)
            if existing is None:
                return {"success": False, "error": "Order not found."}
            return {
                "success": False,
                "error": f"Order must be 'confirmed' or 'processing' to ship (current status: {existing.status.value}).",
            }
        session.commit()
        return {
            "success": True,
            "order_id": order_id,
            "status": OrderStatus.SHIPPED.value,
            "tracking_number": tracking_number,
            "carrier": carrier,
        }


def mark_delivered(order_id: int) -> dict:
    with get_session() as session:
        result = session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.SHIPPED)
            .values(status=OrderStatus.DELIVERED, delivered_at=utcnow())
        )
        if result.rowcount == 0:
            existing = session.get(Order, order_id)
            if existing is None:
                return {"success": False, "error": "Order not found."}
            return {
                "success": False,
                "error": f"Order must be 'shipped' to mark delivered (current status: {existing.status.value}).",
            }
        session.commit()
        return {"success": True, "order_id": order_id, "status": OrderStatus.DELIVERED.value}
