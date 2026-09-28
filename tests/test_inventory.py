"""
Tests for atomic inventory decrement/restore behavior, now going through
the prepare_order -> confirm_order workflow (create_order no longer
exists as a standalone LLM tool — see tools/order_tools.py).
"""

import json
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.models import InventoryItem  # noqa: E402
from db.session import get_session  # noqa: E402
from tools.order_tools import make_order_tools  # noqa: E402


def _prepare_and_confirm(customer_id, conversation_id, items):
    tools = make_order_tools(customer_id, conversation_id)
    prepare = next(t for t in tools if t.name == "prepare_order")
    confirm = next(t for t in tools if t.name == "confirm_order")

    prepared = json.loads(prepare.invoke({"items": items}))
    if not prepared["success"]:
        return prepared
    return json.loads(confirm.invoke({"confirmation_id": prepared["confirmation_id"]}))


def test_order_succeeds_and_decrements_stock(seeded_customers, seeded_inventory):
    result = _prepare_and_confirm("cust-A", "conv-1", [{"sku": "IC-0001", "quantity": 2}])
    assert result["success"] is True

    with get_session() as session:
        assert session.get(InventoryItem, "IC-0001").stock_level == 0


def test_order_fails_when_insufficient_stock_and_stock_unchanged(seeded_customers, seeded_inventory):
    result = _prepare_and_confirm("cust-A", "conv-1", [{"sku": "IC-0002", "quantity": 5}])
    assert result["success"] is False

    with get_session() as session:
        assert session.get(InventoryItem, "IC-0002").stock_level == 1  # unchanged


def test_partial_failure_rolls_back_entire_order(seeded_customers, seeded_inventory):
    result = _prepare_and_confirm(
        "cust-A",
        "conv-1",
        [{"sku": "IC-0001", "quantity": 1}, {"sku": "IC-0002", "quantity": 5}],
    )
    # IC-0002 (qty 5, stock 1) is rejected at prepare_order time already.
    assert result["success"] is False

    with get_session() as session:
        assert session.get(InventoryItem, "IC-0001").stock_level == 2  # unchanged
        assert session.get(InventoryItem, "IC-0002").stock_level == 1  # unchanged


def test_stock_drop_between_prepare_and_confirm_fails_confirm_cleanly(seeded_customers, seeded_inventory):
    """
    prepare_order succeeds (stock was sufficient), but stock is consumed
    by someone else before confirm_order runs. confirm_order must fail
    without double-decrementing, and the confirmation should be usable
    again after retry logic (left to the caller) rather than silently lost.
    """
    tools_a = make_order_tools("cust-A", "conv-1")
    prepare_a = next(t for t in tools_a if t.name == "prepare_order")
    confirm_a = next(t for t in tools_a if t.name == "confirm_order")

    prepared = json.loads(prepare_a.invoke({"items": [{"sku": "IC-0002", "quantity": 1}]}))
    assert prepared["success"] is True

    # Someone else buys the last unit in the meantime.
    result_b = _prepare_and_confirm("cust-B", "conv-2", [{"sku": "IC-0002", "quantity": 1}])
    assert result_b["success"] is True

    # Now customer A's confirm should fail cleanly.
    result_a = json.loads(confirm_a.invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert result_a["success"] is False

    with get_session() as session:
        assert session.get(InventoryItem, "IC-0002").stock_level == 0


def test_concurrent_confirm_for_last_unit_only_one_succeeds(seeded_customers, seeded_inventory):
    """
    Two customers each prepare an order for the single remaining unit of
    IC-0002, then both call confirm_order concurrently. Exactly one must
    succeed.
    """
    tools_a = make_order_tools("cust-A", "conv-1")
    tools_b = make_order_tools("cust-B", "conv-2")
    prepare_a = next(t for t in tools_a if t.name == "prepare_order")
    prepare_b = next(t for t in tools_b if t.name == "prepare_order")
    confirm_a = next(t for t in tools_a if t.name == "confirm_order")
    confirm_b = next(t for t in tools_b if t.name == "confirm_order")

    prepared_a = json.loads(prepare_a.invoke({"items": [{"sku": "IC-0002", "quantity": 1}]}))
    prepared_b = json.loads(prepare_b.invoke({"items": [{"sku": "IC-0002", "quantity": 1}]}))
    assert prepared_a["success"] is True
    assert prepared_b["success"] is True

    results = {}

    def do_confirm(tool, confirmation_id, key):
        results[key] = json.loads(tool.invoke({"confirmation_id": confirmation_id}))

    t1 = threading.Thread(target=do_confirm, args=(confirm_a, prepared_a["confirmation_id"], "a"))
    t2 = threading.Thread(target=do_confirm, args=(confirm_b, prepared_b["confirmation_id"], "b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = [r for r in results.values() if r["success"]]
    assert len(successes) == 1

    with get_session() as session:
        assert session.get(InventoryItem, "IC-0002").stock_level == 0


def test_cancel_order_restores_stock(seeded_customers, seeded_inventory):
    result = _prepare_and_confirm("cust-A", "conv-1", [{"sku": "IC-0001", "quantity": 1}])
    order_id = result["order_id"]

    tools = make_order_tools("cust-A", "conv-1")
    cancel_order = next(t for t in tools if t.name == "cancel_order")
    cancelled = json.loads(cancel_order.invoke({"order_id": order_id}))
    assert cancelled["success"] is True

    with get_session() as session:
        assert session.get(InventoryItem, "IC-0001").stock_level == 2  # restored


def test_concurrent_cancellation_restores_inventory_exactly_once(seeded_customers, seeded_inventory):
    """
    Two simultaneous cancel_order calls for the SAME order: only one may
    succeed, and inventory must be restored exactly once, not twice.
    """
    result = _prepare_and_confirm("cust-A", "conv-1", [{"sku": "IC-0002", "quantity": 1}])
    order_id = result["order_id"]

    with get_session() as session:
        assert session.get(InventoryItem, "IC-0002").stock_level == 0

    tools = make_order_tools("cust-A", "conv-1")
    cancel_order = next(t for t in tools if t.name == "cancel_order")

    results = {}

    def do_cancel(key):
        results[key] = json.loads(cancel_order.invoke({"order_id": order_id}))

    t1 = threading.Thread(target=do_cancel, args=("a",))
    t2 = threading.Thread(target=do_cancel, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = [r for r in results.values() if r["success"]]
    assert len(successes) == 1

    with get_session() as session:
        # Original stock was 1; must be restored to exactly 1, not 2.
        assert session.get(InventoryItem, "IC-0002").stock_level == 1
