"""Tests for the return/refund workflow (Change 4)."""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.models import Order, OrderStatus, Return, ReturnStatus  # noqa: E402
from db.session import get_session  # noqa: E402
from tools.order_tools import make_order_tools  # noqa: E402
from tools.return_tools import approve_return, make_return_tools, process_refund, reject_return  # noqa: E402


def _create_confirmed_order(customer_id="cust-A", conversation_id="conv-1"):
    tools = make_order_tools(customer_id, conversation_id)
    prepare = next(t for t in tools if t.name == "prepare_order")
    confirm = next(t for t in tools if t.name == "confirm_order")
    prepared = json.loads(prepare.invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    confirmed = json.loads(confirm.invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert confirmed["success"] is True
    return confirmed["order_id"]


def test_customer_can_request_return_for_own_order(seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    tools = {t.name: t for t in make_return_tools("cust-A")}

    result = json.loads(tools["request_return"].invoke({"order_id": order_id, "reason": "Wrong part"}))
    assert result["success"] is True

    with get_session() as session:
        assert session.get(Order, order_id).status == OrderStatus.RETURN_REQUESTED


def test_customer_cannot_request_return_for_another_customers_order(seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order("cust-A", "conv-1")
    tools_b = {t.name: t for t in make_return_tools("cust-B")}

    result = json.loads(tools_b["request_return"].invoke({"order_id": order_id, "reason": "Not mine"}))
    assert result["success"] is False


def test_return_status_is_ownership_checked(seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    tools_a = {t.name: t for t in make_return_tools("cust-A")}
    requested = json.loads(tools_a["request_return"].invoke({"order_id": order_id, "reason": "Defective"}))
    return_id = requested["return_id"]

    tools_b = {t.name: t for t in make_return_tools("cust-B")}
    result = json.loads(tools_b["get_return_status"].invoke({"return_id": return_id}))
    assert result["success"] is False

    result_owner = json.loads(tools_a["get_return_status"].invoke({"return_id": return_id}))
    assert result_owner["success"] is True
    assert result_owner["status"] == "requested"


def test_refund_cannot_happen_before_approval(seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    tools_a = {t.name: t for t in make_return_tools("cust-A")}
    requested = json.loads(tools_a["request_return"].invoke({"order_id": order_id, "reason": "Defective"}))
    return_id = requested["return_id"]

    result = process_refund(return_id)
    assert result["success"] is False

    with get_session() as session:
        assert session.get(Return, return_id).status == ReturnStatus.REQUESTED


def test_approve_then_refund_succeeds(seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    tools_a = {t.name: t for t in make_return_tools("cust-A")}
    requested = json.loads(tools_a["request_return"].invoke({"order_id": order_id, "reason": "Defective"}))
    return_id = requested["return_id"]

    approved = approve_return(return_id, resolution="Confirmed defective on inspection")
    assert approved["success"] is True

    refunded = process_refund(return_id)
    assert refunded["success"] is True

    with get_session() as session:
        assert session.get(Return, return_id).status == ReturnStatus.REFUNDED
        assert session.get(Order, order_id).status == OrderStatus.REFUNDED


def test_refund_cannot_happen_twice(seeded_customers, seeded_inventory):
    """✓ Duplicate refund prevention."""
    order_id = _create_confirmed_order()
    tools_a = {t.name: t for t in make_return_tools("cust-A")}
    requested = json.loads(tools_a["request_return"].invoke({"order_id": order_id, "reason": "Defective"}))
    return_id = requested["return_id"]
    approve_return(return_id)

    first = process_refund(return_id)
    second = process_refund(return_id)

    assert first["success"] is True
    assert second["success"] is False


def test_reject_return_restores_prior_order_status(seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    tools_a = {t.name: t for t in make_return_tools("cust-A")}
    requested = json.loads(tools_a["request_return"].invoke({"order_id": order_id, "reason": "Changed my mind"}))
    return_id = requested["return_id"]

    rejected = reject_return(return_id, resolution="Outside return window")
    assert rejected["success"] is True

    with get_session() as session:
        assert session.get(Order, order_id).status == OrderStatus.CONFIRMED  # restored
        assert session.get(Return, return_id).status == ReturnStatus.REJECTED


def test_cannot_request_return_on_already_cancelled_order(seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    order_tools = {t.name: t for t in make_order_tools("cust-A", "conv-1")}
    cancelled = json.loads(order_tools["cancel_order"].invoke({"order_id": order_id}))
    assert cancelled["success"] is True

    return_tools = {t.name: t for t in make_return_tools("cust-A")}
    result = json.loads(return_tools["request_return"].invoke({"order_id": order_id, "reason": "test"}))
    assert result["success"] is False


def test_return_tools_do_not_expose_customer_id_param(seeded_customers, seeded_inventory):
    tools = make_return_tools("cust-A")
    for t in tools:
        props = t.args_schema.model_json_schema()["properties"]
        assert "customer_id" not in props
