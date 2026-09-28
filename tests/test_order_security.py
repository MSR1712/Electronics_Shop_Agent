"""Tests that a customer can never read or affect another customer's orders."""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools.order_tools import make_order_tools  # noqa: E402


def _prepare_and_confirm(customer_id, conversation_id, items):
    tools = make_order_tools(customer_id, conversation_id)
    prepare = next(t for t in tools if t.name == "prepare_order")
    confirm = next(t for t in tools if t.name == "confirm_order")
    prepared = json.loads(prepare.invoke({"items": items}))
    assert prepared["success"] is True
    return json.loads(confirm.invoke({"confirmation_id": prepared["confirmation_id"]}))


def test_customer_cannot_see_another_customers_order(seeded_customers, seeded_inventory):
    created = _prepare_and_confirm("cust-A", "conv-1", [{"sku": "IC-0001", "quantity": 1}])
    order_id = created["order_id"]

    tools_b = make_order_tools("cust-B", "conv-2")
    get_status_b = next(t for t in tools_b if t.name == "get_order_status")
    result = json.loads(get_status_b.invoke({"order_id": order_id}))

    assert result["success"] is False
    assert "not found" in result["error"].lower()
    assert "cust-A" not in json.dumps(result)


def test_customer_cannot_cancel_another_customers_order(seeded_customers, seeded_inventory):
    created = _prepare_and_confirm("cust-A", "conv-1", [{"sku": "IC-0001", "quantity": 1}])
    order_id = created["order_id"]

    tools_b = make_order_tools("cust-B", "conv-2")
    cancel_b = next(t for t in tools_b if t.name == "cancel_order")
    result = json.loads(cancel_b.invoke({"order_id": order_id}))

    assert result["success"] is False


def test_owner_can_see_their_own_order(seeded_customers, seeded_inventory):
    created = _prepare_and_confirm("cust-A", "conv-1", [{"sku": "IC-0001", "quantity": 1}])

    tools_a = make_order_tools("cust-A", "conv-1")
    get_status_a = next(t for t in tools_a if t.name == "get_order_status")
    result = json.loads(get_status_a.invoke({"order_id": created["order_id"]}))

    assert result["success"] is True
    assert result["order_id"] == created["order_id"]


def test_no_tool_exposes_customer_id_or_conversation_id_as_a_param(seeded_customers, seeded_inventory):
    """
    Regression guard for the core security fix: none of the LLM-facing
    order tool schemas expose customer_id or conversation_id — it must be
    impossible for the model to name a different identity.
    """
    tools = make_order_tools("cust-A", "conv-1")
    for t in tools:
        props = t.args_schema.model_json_schema()["properties"]
        assert "customer_id" not in props, f"{t.name} leaks customer_id"
        assert "conversation_id" not in props, f"{t.name} leaks conversation_id"


def test_wrong_customer_cannot_confirm_anothers_pending_order(seeded_customers, seeded_inventory):
    """Change 1: confirmation is customer-scoped, not just order-scoped."""
    tools_a = make_order_tools("cust-A", "conv-1")
    prepare_a = next(t for t in tools_a if t.name == "prepare_order")
    prepared = json.loads(prepare_a.invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    assert prepared["success"] is True

    tools_b = make_order_tools("cust-B", "conv-1")  # same conversation_id, different customer
    confirm_b = next(t for t in tools_b if t.name == "confirm_order")
    result = json.loads(confirm_b.invoke({"confirmation_id": prepared["confirmation_id"]}))

    assert result["success"] is False


def test_wrong_conversation_cannot_confirm_same_customers_order(seeded_customers, seeded_inventory):
    """Change 1: confirmation is conversation-scoped, not just customer-scoped."""
    tools_conv1 = make_order_tools("cust-A", "conv-1")
    prepare = next(t for t in tools_conv1 if t.name == "prepare_order")
    prepared = json.loads(prepare.invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    assert prepared["success"] is True

    tools_conv2 = make_order_tools("cust-A", "conv-2")  # same customer, different conversation
    confirm_conv2 = next(t for t in tools_conv2 if t.name == "confirm_order")
    result = json.loads(confirm_conv2.invoke({"confirmation_id": prepared["confirmation_id"]}))

    assert result["success"] is False
