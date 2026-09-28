"""Tests that money is handled as integer cents throughout, never float."""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.models import InventoryItem  # noqa: E402
from db.session import get_session  # noqa: E402
from tools.order_tools import make_order_tools  # noqa: E402


def test_inventory_price_is_stored_as_integer_cents(seeded_inventory):
    with get_session() as session:
        inv = session.get(InventoryItem, "IC-0001")
        assert isinstance(inv.price_cents, int)
        assert inv.price_cents == 199
        assert inv.price_usd == Decimal("1.99")


def test_order_total_is_exact_no_float_rounding(seeded_customers, seeded_inventory):
    """
    1 unit at $1.99 (199 cents). This is a case where naive float
    arithmetic can drift — cents arithmetic must not.
    """
    tools = {t.name: t for t in make_order_tools("cust-A", "conv-1")}
    prepared = json.loads(tools["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    confirmed = json.loads(tools["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))

    assert confirmed["total_cents"] == 199
    assert confirmed["total_display"] == "$1.99"


def test_multi_quantity_total_is_exact(seeded_customers, seeded_inventory):
    """3 x 199 cents = 597 cents exactly — a case where 1.99 * 3 in float
    can produce 5.970000000000001 in Python."""
    with get_session() as session:
        inv = session.get(InventoryItem, "IC-0001")
        inv.stock_level = 10
        session.commit()

    tools = {t.name: t for t in make_order_tools("cust-A", "conv-1")}
    prepared = json.loads(tools["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 3}]}))
    assert prepared["total_cents"] == 597

    confirmed = json.loads(tools["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert confirmed["total_cents"] == 597
    assert confirmed["total_display"] == "$5.97"
