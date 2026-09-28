"""
Admin/back-office endpoints behind api/admin_session.py's admin cookie.

This is the "admin surface" the README's known limitations call for: every
state-changing action here calls the existing atomic functions in
tools/return_tools.py (approve_return / reject_return / process_refund) and
tools/fulfillment_tools.py (mark_processing / mark_shipped / mark_delivered)
rather than reimplementing any transition. None of these are agent tools,
and no customer session can reach them.

The only writes implemented directly here are escalation triage (a plain
support-queue record) and inventory price/stock edits, the latter as an
atomic conditional UPDATE so a stock adjustment can never drive
stock_level negative, even racing a concurrent order.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, update

from db.models import (
    Customer,
    Escalation,
    EscalationStatus,
    InventoryItem,
    Order,
    OrderStatus,
    Return,
    ReturnStatus,
)
from db.session import get_session
from tools.fulfillment_tools import mark_delivered, mark_processing, mark_shipped
from tools.return_tools import approve_return, process_refund, reject_return

from api.admin_session import ADMIN_COOKIE_NAME, check_admin_password, issue_admin_session, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

LOW_STOCK_THRESHOLD = 5
LIST_LIMIT = 200


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class ShipRequest(BaseModel):
    tracking_number: str = Field(min_length=1, max_length=100)
    carrier: str | None = Field(default=None, max_length=100)


class ResolutionRequest(BaseModel):
    resolution: str | None = Field(default=None, max_length=2000)


class EscalationUpdateRequest(BaseModel):
    status: EscalationStatus | None = None
    assigned_agent: str | None = Field(default=None, max_length=200)
    resolution: str | None = Field(default=None, max_length=2000)


class InventoryUpdateRequest(BaseModel):
    price_cents: int | None = Field(default=None, ge=0)
    # A relative adjustment (+restock / -write-off), not an absolute value,
    # so it composes safely with orders decrementing stock concurrently.
    stock_delta: int | None = None


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _unwrap(result: dict) -> dict:
    """Same convention as api/routers/checkout.py: a tool/admin function's
    own {success: false, error} dict becomes the 400 detail verbatim."""
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


def _order_summary(order: Order, customer_name: str | None) -> dict:
    return {
        "order_id": order.id,
        "customer_id": order.customer_id,
        "customer_name": customer_name,
        "status": order.status.value,
        "created_at": _iso(order.created_at),
        "item_count": sum(i.quantity for i in order.items),
        "total_cents": order.total_cents,
        "tracking_number": order.tracking_number,
        "carrier": order.carrier,
    }


def _return_dict(ret: Return, customer_name: str | None = None) -> dict:
    return {
        "return_id": ret.id,
        "order_id": ret.order_id,
        "customer_id": ret.customer_id,
        "customer_name": customer_name,
        "reason": ret.reason,
        "status": ret.status.value,
        "resolution": ret.resolution,
        "created_at": _iso(ret.created_at),
        "updated_at": _iso(ret.updated_at),
    }


def _escalation_dict(esc: Escalation, customer_name: str | None) -> dict:
    return {
        "escalation_id": esc.id,
        "customer_id": esc.customer_id,
        "customer_name": customer_name,
        "conversation_id": esc.conversation_id,
        "reason": esc.reason,
        "status": esc.status.value,
        "assigned_agent": esc.assigned_agent,
        "resolution": esc.resolution,
        "created_at": _iso(esc.created_at),
        "updated_at": _iso(esc.updated_at),
    }


def _inventory_dict(item: InventoryItem) -> dict:
    return {
        "sku": item.sku,
        "name": item.name,
        "price_cents": item.price_cents,
        "stock_level": item.stock_level,
    }


# --- Auth -------------------------------------------------------------------

@router.post("/login")
def admin_login(payload: AdminLoginRequest, response: Response):
    if not check_admin_password(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect admin password.")
    issue_admin_session(response)
    return {"success": True}


@router.post("/logout")
def admin_logout(response: Response):
    response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
    return {"success": True}


@router.get("/me", dependencies=[Depends(require_admin)])
def admin_me():
    return {"admin": True}


# --- Dashboard --------------------------------------------------------------

@router.get("/summary", dependencies=[Depends(require_admin)])
def admin_summary():
    with get_session() as session:
        orders_by_status = {s.value: 0 for s in OrderStatus}
        for status, count in session.query(Order.status, func.count(Order.id)).group_by(Order.status):
            orders_by_status[status.value] = count

        returns_by_status = {s.value: 0 for s in ReturnStatus}
        for status, count in session.query(Return.status, func.count(Return.id)).group_by(Return.status):
            returns_by_status[status.value] = count

        open_escalations = (
            session.query(func.count(Escalation.id))
            .filter(Escalation.status.notin_([EscalationStatus.RESOLVED, EscalationStatus.CLOSED]))
            .scalar()
        )
        low_stock = (
            session.query(func.count(InventoryItem.sku))
            .filter(InventoryItem.stock_level <= LOW_STOCK_THRESHOLD)
            .scalar()
        )
        return {
            "orders_by_status": orders_by_status,
            "returns_by_status": returns_by_status,
            "open_escalations": open_escalations,
            "low_stock_count": low_stock,
            "low_stock_threshold": LOW_STOCK_THRESHOLD,
        }


# --- Orders / fulfillment ---------------------------------------------------

@router.get("/orders", dependencies=[Depends(require_admin)])
def admin_list_orders(status: OrderStatus | None = None):
    with get_session() as session:
        query = session.query(Order, Customer.name).outerjoin(Customer, Customer.id == Order.customer_id)
        if status is not None:
            query = query.filter(Order.status == status)
        rows = query.order_by(Order.id.desc()).limit(LIST_LIMIT).all()
        return {"orders": [_order_summary(order, name) for order, name in rows]}


@router.get("/orders/{order_id}", dependencies=[Depends(require_admin)])
def admin_order_detail(order_id: int):
    with get_session() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail={"success": False, "error": "Order not found."})
        customer = session.get(Customer, order.customer_id)
        detail = _order_summary(order, customer.name if customer else None)
        detail.update(
            {
                "customer_email": customer.email if customer else None,
                "shipped_at": _iso(order.shipped_at),
                "delivered_at": _iso(order.delivered_at),
                "items": [
                    {
                        "sku": i.sku,
                        "name": i.inventory_item.name if i.inventory_item else None,
                        "quantity": i.quantity,
                        "unit_price_cents": i.unit_price_cents,
                    }
                    for i in order.items
                ],
                "returns": [_return_dict(r) for r in order.returns],
            }
        )
        return detail


@router.post("/orders/{order_id}/processing", dependencies=[Depends(require_admin)])
def admin_mark_processing(order_id: int):
    return _unwrap(mark_processing(order_id))


@router.post("/orders/{order_id}/ship", dependencies=[Depends(require_admin)])
def admin_mark_shipped(order_id: int, payload: ShipRequest):
    return _unwrap(mark_shipped(order_id, payload.tracking_number.strip(), (payload.carrier or "").strip() or None))


@router.post("/orders/{order_id}/deliver", dependencies=[Depends(require_admin)])
def admin_mark_delivered(order_id: int):
    return _unwrap(mark_delivered(order_id))


# --- Returns / refunds ------------------------------------------------------

@router.get("/returns", dependencies=[Depends(require_admin)])
def admin_list_returns(status: ReturnStatus | None = None):
    with get_session() as session:
        query = session.query(Return, Customer.name).outerjoin(Customer, Customer.id == Return.customer_id)
        if status is not None:
            query = query.filter(Return.status == status)
        rows = query.order_by(Return.id.desc()).limit(LIST_LIMIT).all()
        return {"returns": [_return_dict(ret, name) for ret, name in rows]}


@router.post("/returns/{return_id}/approve", dependencies=[Depends(require_admin)])
def admin_approve_return(return_id: int, payload: ResolutionRequest):
    return _unwrap(approve_return(return_id, payload.resolution))


@router.post("/returns/{return_id}/reject", dependencies=[Depends(require_admin)])
def admin_reject_return(return_id: int, payload: ResolutionRequest):
    return _unwrap(reject_return(return_id, payload.resolution))


@router.post("/returns/{return_id}/refund", dependencies=[Depends(require_admin)])
def admin_process_refund(return_id: int):
    return _unwrap(process_refund(return_id))


# --- Escalations ------------------------------------------------------------

@router.get("/escalations", dependencies=[Depends(require_admin)])
def admin_list_escalations(status: EscalationStatus | None = None):
    with get_session() as session:
        query = session.query(Escalation, Customer.name).outerjoin(Customer, Customer.id == Escalation.customer_id)
        if status is not None:
            query = query.filter(Escalation.status == status)
        rows = query.order_by(Escalation.id.desc()).limit(LIST_LIMIT).all()
        return {"escalations": [_escalation_dict(esc, name) for esc, name in rows]}


@router.patch("/escalations/{escalation_id}", dependencies=[Depends(require_admin)])
def admin_update_escalation(escalation_id: int, payload: EscalationUpdateRequest):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail={"success": False, "error": "Nothing to update."})
    with get_session() as session:
        esc = session.get(Escalation, escalation_id)
        if esc is None:
            raise HTTPException(status_code=404, detail={"success": False, "error": "Escalation not found."})
        for field, value in changes.items():
            setattr(esc, field, value)
        session.commit()
        customer = session.get(Customer, esc.customer_id)
        return {"success": True, **_escalation_dict(esc, customer.name if customer else None)}


# --- Inventory --------------------------------------------------------------

@router.get("/inventory", dependencies=[Depends(require_admin)])
def admin_list_inventory(q: str | None = None, low_stock: bool = False, limit: int = Query(default=100, ge=1, le=500)):
    # Server-side search + limit: an imported catalog can have tens of
    # thousands of SKUs, far too many to ship to the browser in one go.
    with get_session() as session:
        query = session.query(InventoryItem)
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            query = query.filter(or_(InventoryItem.sku.ilike(pattern), InventoryItem.name.ilike(pattern)))
        if low_stock:
            query = query.filter(InventoryItem.stock_level <= LOW_STOCK_THRESHOLD)
        total = query.count()
        order = InventoryItem.stock_level if low_stock else InventoryItem.sku
        items = query.order_by(order, InventoryItem.sku).limit(limit).all()
        return {"items": [_inventory_dict(i) for i in items], "total": total}


@router.patch("/inventory/{sku}", dependencies=[Depends(require_admin)])
def admin_update_inventory(sku: str, payload: InventoryUpdateRequest):
    if payload.price_cents is None and not payload.stock_delta:
        raise HTTPException(status_code=400, detail={"success": False, "error": "Nothing to update."})
    with get_session() as session:
        item = session.get(InventoryItem, sku)
        if item is None:
            raise HTTPException(status_code=404, detail={"success": False, "error": "SKU not found."})

        values = {}
        conditions = [InventoryItem.sku == sku]
        if payload.price_cents is not None:
            values["price_cents"] = payload.price_cents
        if payload.stock_delta:
            values["stock_level"] = InventoryItem.stock_level + payload.stock_delta
            conditions.append(InventoryItem.stock_level + payload.stock_delta >= 0)

        result = session.execute(update(InventoryItem).where(*conditions).values(**values))
        if result.rowcount == 0:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": f"Stock can't go below 0 (current stock: {item.stock_level})."},
            )
        session.commit()
        session.refresh(item)
        return {"success": True, **_inventory_dict(item)}
