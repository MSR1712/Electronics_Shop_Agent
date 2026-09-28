"""
Return/refund workflow.

Customer-facing tools (bound to customer_id, exposed to order_agent):
  - request_return: the ONLY action a customer/LLM can trigger. Creates a
    REQUESTED row and moves the order to RETURN_REQUESTED. It does not
    approve anything and does not refund anything.
  - get_return_status: ownership-checked read.

Internal/admin functions (NOT decorated as agent tools, NOT wired into any
LangGraph node): approve_return, reject_return, process_refund. In a real
deployment these would be called from a back-office/admin tool or an
internal support dashboard — never from the customer-facing chat agent.
This is deliberate: "the customer-facing agent should not directly decide
that a refund has happened" from the spec. If you want the escalation
agent's human handoff to eventually trigger these, that's a human acting
through an admin surface, not the LLM calling a tool.
"""

import json

from langchain_core.tools import tool
from sqlalchemy import update

from db.models import (
    RETURNABLE_ORDER_STATUSES,
    Order,
    OrderStatus,
    Return,
    ReturnStatus,
)
from db.session import get_session


def make_return_tools(customer_id: str):
    """Returns [request_return, get_return_status] bound to customer_id."""

    @tool
    def request_return(order_id: int, reason: str) -> str:
        """
        Requests a return for one of the customer's own orders. Only
        creates a return request — approval and refund happen separately
        through the business's own process, not through this tool.
        `reason` should briefly describe why the customer wants to return it.
        """
        with get_session() as session:
            order = (
                session.query(Order)
                .filter(Order.id == order_id, Order.customer_id == customer_id)
                .first()
            )
            if order is None:
                return json.dumps({"success": False, "error": "Order not found."})

            if order.status not in RETURNABLE_ORDER_STATUSES:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Order is '{order.status.value}' and is not eligible for a return request.",
                    }
                )

            existing_open = (
                session.query(Return)
                .filter(Return.order_id == order_id, Return.status == ReturnStatus.REQUESTED)
                .first()
            )
            if existing_open is not None:
                return json.dumps(
                    {"success": False, "error": f"A return (#{existing_open.id}) is already pending for this order."}
                )

            ret = Return(
                order_id=order.id,
                customer_id=customer_id,
                reason=reason,
                status=ReturnStatus.REQUESTED,
                pre_return_order_status=order.status,
            )
            session.add(ret)
            order.status = OrderStatus.RETURN_REQUESTED
            session.commit()
            session.refresh(ret)

            return json.dumps(
                {
                    "success": True,
                    "return_id": ret.id,
                    "order_id": order.id,
                    "status": ret.status.value,
                    "note": "Return requested. A member of our team will review it — this does "
                    "not guarantee approval or a refund.",
                }
            )

    @tool
    def get_return_status(return_id: int) -> str:
        """Looks up the status of a return request, for the current authenticated customer only."""
        with get_session() as session:
            ret = (
                session.query(Return)
                .filter(Return.id == return_id, Return.customer_id == customer_id)
                .first()
            )
            if ret is None:
                return json.dumps({"success": False, "error": "Return not found."})

            return json.dumps(
                {
                    "success": True,
                    "return_id": ret.id,
                    "order_id": ret.order_id,
                    "status": ret.status.value,
                    "resolution": ret.resolution,
                    "created_at": ret.created_at.isoformat(),
                }
            )

    return [request_return, get_return_status]


# ---------------------------------------------------------------------------
# Internal/admin operations — NOT LLM tools. Call these from an admin
# script, internal dashboard, or (later) a human-response-driven resume of
# an escalation. Each is an atomic conditional transition, following the
# same pattern as order confirmation/cancellation, so double-approval and
# double-refund are structurally prevented, not just discouraged.
# ---------------------------------------------------------------------------

def approve_return(return_id: int, resolution: str | None = None) -> dict:
    with get_session() as session:
        result = session.execute(
            update(Return)
            .where(Return.id == return_id, Return.status == ReturnStatus.REQUESTED)
            .values(status=ReturnStatus.APPROVED, resolution=resolution)
        )
        if result.rowcount == 0:
            return {"success": False, "error": "Return not found or not in a requestable state."}
        session.commit()
        return {"success": True, "return_id": return_id, "status": ReturnStatus.APPROVED.value}


def reject_return(return_id: int, resolution: str | None = None) -> dict:
    with get_session() as session:
        ret = session.get(Return, return_id)
        if ret is None or ret.status != ReturnStatus.REQUESTED:
            return {"success": False, "error": "Return not found or not in a requestable state."}

        result = session.execute(
            update(Return)
            .where(Return.id == return_id, Return.status == ReturnStatus.REQUESTED)
            .values(status=ReturnStatus.REJECTED, resolution=resolution)
        )
        if result.rowcount == 0:
            return {"success": False, "error": "Return could not be rejected (already resolved)."}

        # Restore the order to whatever it was before the return request.
        session.execute(
            update(Order).where(Order.id == ret.order_id).values(status=ret.pre_return_order_status)
        )
        session.commit()
        return {"success": True, "return_id": return_id, "status": ReturnStatus.REJECTED.value}


def process_refund(return_id: int) -> dict:
    """
    Refunds an APPROVED return exactly once. The APPROVED -> REFUNDED
    transition is the atomic conditional update that makes double-refund
    structurally impossible: a second call sees rowcount 0 because the
    first call already moved the status off APPROVED.
    """
    with get_session() as session:
        result = session.execute(
            update(Return)
            .where(Return.id == return_id, Return.status == ReturnStatus.APPROVED)
            .values(status=ReturnStatus.REFUNDED)
        )
        if result.rowcount == 0:
            existing = session.get(Return, return_id)
            if existing is None:
                return {"success": False, "error": "Return not found."}
            if existing.status == ReturnStatus.REFUNDED:
                return {"success": False, "error": "This return has already been refunded."}
            return {"success": False, "error": f"Return must be approved before refunding (current status: {existing.status.value})."}

        ret = session.get(Return, return_id)
        session.execute(update(Order).where(Order.id == ret.order_id).values(status=OrderStatus.REFUNDED))
        session.commit()
        return {"success": True, "return_id": return_id, "status": ReturnStatus.REFUNDED.value}
