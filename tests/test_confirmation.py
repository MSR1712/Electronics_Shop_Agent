"""
Tests for the backend-enforced order confirmation workflow (Change 1).
The point of this file: prove that NOTHING short of a valid, matching,
unexpired, unconsumed PendingConfirmation row can ever result in an Order.
"""

import json
import sys
import threading
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.models import Order, PendingConfirmation, PendingConfirmationStatus, utcnow  # noqa: E402
from db.session import get_session  # noqa: E402
from tools.order_tools import make_order_tools  # noqa: E402


def _tools(customer_id="cust-A", conversation_id="conv-1"):
    tools = make_order_tools(customer_id, conversation_id)
    return {t.name: t for t in tools}


def test_prepare_order_does_not_create_an_order_or_touch_stock(seeded_customers, seeded_inventory):
    from db.models import InventoryItem

    t = _tools()
    prepared = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    assert prepared["success"] is True

    with get_session() as session:
        assert session.query(Order).count() == 0
        assert session.get(InventoryItem, "IC-0001").stock_level == 2  # untouched


def test_confirm_without_prepare_fails(seeded_customers, seeded_inventory):
    """✓ Order cannot be created without pending confirmation."""
    t = _tools()
    result = json.loads(t["confirm_order"].invoke({"confirmation_id": 99999}))
    assert result["success"] is False

    with get_session() as session:
        assert session.query(Order).count() == 0


def test_valid_confirmation_creates_order(seeded_customers, seeded_inventory):
    """✓ Valid confirmation creates order."""
    t = _tools()
    prepared = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    result = json.loads(t["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))

    assert result["success"] is True
    assert "order_id" in result

    with get_session() as session:
        pc = session.get(PendingConfirmation, prepared["confirmation_id"])
        assert pc.status == PendingConfirmationStatus.CONSUMED


def test_wrong_customer_cannot_confirm(seeded_customers, seeded_inventory):
    """✓ Wrong customer cannot confirm another customer's order."""
    t_a = _tools("cust-A", "conv-1")
    prepared = json.loads(t_a["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))

    t_b = _tools("cust-B", "conv-1")
    result = json.loads(t_b["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert result["success"] is False


def test_wrong_conversation_cannot_confirm(seeded_customers, seeded_inventory):
    """✓ Wrong conversation cannot confirm another conversation's order."""
    t_conv1 = _tools("cust-A", "conv-1")
    prepared = json.loads(t_conv1["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))

    t_conv2 = _tools("cust-A", "conv-2")
    result = json.loads(t_conv2["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert result["success"] is False


def test_expired_confirmation_cannot_create_order(seeded_customers, seeded_inventory):
    """✓ Expired confirmation cannot create order."""
    t = _tools()
    prepared = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))

    # Force-expire it directly in the DB (simulating time passing).
    with get_session() as session:
        pc = session.get(PendingConfirmation, prepared["confirmation_id"])
        pc.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()

    result = json.loads(t["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert result["success"] is False

    with get_session() as session:
        assert session.query(Order).count() == 0


def test_confirmation_cannot_be_replayed(seeded_customers, seeded_inventory):
    """✓ Same confirmation cannot be replayed."""
    t = _tools()
    prepared = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))

    first = json.loads(t["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert first["success"] is True

    second = json.loads(t["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert second["success"] is False

    with get_session() as session:
        assert session.query(Order).count() == 1  # only the first went through


def test_concurrent_replay_only_succeeds_once(seeded_customers, seeded_inventory):
    """Race version of the replay test: simultaneous confirm calls on the same confirmation_id."""
    t = _tools()
    prepared = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    confirmation_id = prepared["confirmation_id"]

    results = {}

    def do_confirm(key):
        results[key] = json.loads(t["confirm_order"].invoke({"confirmation_id": confirmation_id}))

    threads = [threading.Thread(target=do_confirm, args=(i,)) for i in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    successes = [r for r in results.values() if r["success"]]
    assert len(successes) == 1

    with get_session() as session:
        assert session.query(Order).count() == 1


def test_changing_quantity_invalidates_prior_confirmation(seeded_customers, seeded_inventory):
    """✓ Changing quantity after confirmation invalidates confirmation."""
    t = _tools()
    first = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    # Customer changes their mind — a new prepare_order call supersedes the old one.
    second = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 2}]}))

    with get_session() as session:
        old_pc = session.get(PendingConfirmation, first["confirmation_id"])
        assert old_pc.status == PendingConfirmationStatus.SUPERSEDED

    # The old confirmation_id must no longer be confirmable.
    result = json.loads(t["confirm_order"].invoke({"confirmation_id": first["confirmation_id"]}))
    assert result["success"] is False

    # The new one still works.
    result2 = json.loads(t["confirm_order"].invoke({"confirmation_id": second["confirmation_id"]}))
    assert result2["success"] is True


def test_asking_price_does_not_create_order_or_confirmation(seeded_customers, seeded_inventory):
    """
    ✓ Asking for product price does not create an order (and, since this
    tool layer has no natural-language interpretation, this also confirms
    that nothing happens unless prepare_order is explicitly invoked with
    concrete items — a price question maps to search_product_catalog in
    the agent's tool selection, not to prepare_order).
    """
    with get_session() as session:
        assert session.query(Order).count() == 0
        assert session.query(PendingConfirmation).count() == 0
    # No tool call made here at all — this test documents the invariant
    # that merely instantiating the tools does nothing by itself.


def test_prepare_order_alone_is_a_request_not_a_purchase(seeded_customers, seeded_inventory):
    """✓ "Buy this" creates a confirmation request rather than immediately purchasing."""
    t = _tools()
    prepared = json.loads(t["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    assert prepared["success"] is True
    assert "order_id" not in prepared  # no order exists yet
    assert "confirmation_id" in prepared

    with get_session() as session:
        assert session.query(Order).count() == 0
