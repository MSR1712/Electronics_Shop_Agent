"""
Checkout + order endpoints. This is the ONLY place in api/ that touches
orders, and it does so purely by calling the existing prepare_order /
confirm_order / get_order_status / cancel_order StructuredTools via
.invoke(...) — no order-creation, inventory-decrement, or cancellation
logic is reimplemented here. See tools/order_tools.py for the actual
atomicity/ownership/money guarantees.
"""

import json

from fastapi import APIRouter, Depends, HTTPException

from tools.order_tools import make_order_tools

from api.schemas import ConfirmCheckoutRequest, PrepareCheckoutRequest
from api.session import SessionData, require_session

router = APIRouter(prefix="/api", tags=["checkout"])


def _order_tools(session_data: SessionData) -> dict:
    return {t.name: t for t in make_order_tools(session_data.customer_id, session_data.conversation_id)}


@router.post("/checkout/prepare")
def checkout_prepare(payload: PrepareCheckoutRequest, session_data: SessionData = Depends(require_session)):
    tools = _order_tools(session_data)
    result = json.loads(tools["prepare_order"].invoke({"items": [i.model_dump() for i in payload.items]}))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/checkout/confirm")
def checkout_confirm(payload: ConfirmCheckoutRequest, session_data: SessionData = Depends(require_session)):
    tools = _order_tools(session_data)
    result = json.loads(tools["confirm_order"].invoke({"confirmation_id": payload.confirmation_id}))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/orders")
def list_orders(session_data: SessionData = Depends(require_session)):
    tools = _order_tools(session_data)
    return json.loads(tools["list_orders"].invoke({}))


@router.get("/orders/{order_id}")
def order_status(order_id: int, session_data: SessionData = Depends(require_session)):
    tools = _order_tools(session_data)
    result = json.loads(tools["get_order_status"].invoke({"order_id": order_id}))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result)
    return result


@router.post("/orders/{order_id}/cancel")
def order_cancel(order_id: int, session_data: SessionData = Depends(require_session)):
    tools = _order_tools(session_data)
    result = json.loads(tools["cancel_order"].invoke({"order_id": order_id}))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result
