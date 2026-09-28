"""
Tests that price and stock are always sourced from SQL, never from Chroma,
even when Chroma's cached metadata is stale or nonexistent for those
fields. Uses a fake vectorstore (no real Chroma/embedding API call needed)
since what's under test is the join logic in tools/product_tools.py, not
Chroma's own retrieval quality.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parent.parent))

import tools.product_tools as product_tools  # noqa: E402
from db.models import InventoryItem  # noqa: E402
from db.session import get_session  # noqa: E402


class _FakeDoc(SimpleNamespace):
    pass


class _FakeStore:
    """Returns a single canned match for SKU IC-0001, with NO price/stock
    in its metadata — proving the tool cannot use Chroma for those even if
    it wanted to, because Chroma never carries them in this architecture."""

    def similarity_search_with_relevance_scores(self, query, k=4):
        doc = _FakeDoc(
            page_content="Test Chip (IC)\nA test chip for unit tests.\nSpecs: voltage: 5V",
            metadata={"sku": "IC-0001", "name": "Test Chip", "category": "IC"},
        )
        return [(doc, 0.91)]


class _FakeStoreNoRelevantMatch:
    def similarity_search_with_relevance_scores(self, query, k=4):
        doc = _FakeDoc(page_content="irrelevant", metadata={"sku": "IC-9999", "name": "X", "category": "IC"})
        return [(doc, 0.1)]  # below MIN_RELEVANCE


def test_chroma_identifies_sku_and_sql_supplies_current_price_and_stock(
    monkeypatch, seeded_inventory
):
    monkeypatch.setattr(product_tools, "get_product_vectorstore", lambda: _FakeStore())

    result = json.loads(product_tools.search_product_catalog.invoke({"query": "test chip", "k": 4}))
    assert result["found"] is True
    product = result["products"][0]
    assert product["sku"] == "IC-0001"
    # Values must match the SQL fixture (199 cents, stock 2), NOT anything
    # embedded in the fake Chroma doc (which had none).
    assert product["price_cents"] == 199
    assert product["stock_level"] == 2


def test_changing_sql_price_is_reflected_immediately_without_reingesting_chroma(
    monkeypatch, seeded_inventory
):
    monkeypatch.setattr(product_tools, "get_product_vectorstore", lambda: _FakeStore())

    with get_session() as session:
        inv = session.get(InventoryItem, "IC-0001")
        inv.price_cents = 999
        session.commit()

    result = json.loads(product_tools.search_product_catalog.invoke({"query": "test chip", "k": 4}))
    assert result["products"][0]["price_cents"] == 999


def test_changing_sql_stock_is_reflected_immediately(monkeypatch, seeded_inventory):
    monkeypatch.setattr(product_tools, "get_product_vectorstore", lambda: _FakeStore())

    with get_session() as session:
        inv = session.get(InventoryItem, "IC-0001")
        inv.stock_level = 0
        session.commit()

    result = json.loads(product_tools.search_product_catalog.invoke({"query": "test chip", "k": 4}))
    assert result["products"][0]["stock_level"] == 0


def test_missing_sql_record_does_not_invent_price_or_stock(monkeypatch, test_db):
    """SKU exists in Chroma's index but has no SQL inventory row (e.g. discontinued)."""
    monkeypatch.setattr(product_tools, "get_product_vectorstore", lambda: _FakeStore())

    result = json.loads(product_tools.search_product_catalog.invoke({"query": "test chip", "k": 4}))
    product = result["products"][0]
    assert product["price_cents"] is None
    assert product["stock_level"] is None
    assert "availability_note" in product


def test_irrelevant_query_is_rejected_not_answered(monkeypatch, seeded_inventory):
    monkeypatch.setattr(product_tools, "get_product_vectorstore", lambda: _FakeStoreNoRelevantMatch())

    result = json.loads(product_tools.search_product_catalog.invoke({"query": "banana", "k": 4}))
    assert result["found"] is False


def test_order_confirmation_uses_sql_price_not_a_stale_value(seeded_customers, seeded_inventory):
    """
    Change 2's core guarantee end-to-end: even if some other layer had a
    stale price cached, prepare_order/confirm_order (order_tools.py) only
    ever reads InventoryItem.price_cents fresh at call time.
    """
    from tools.order_tools import make_order_tools

    with get_session() as session:
        inv = session.get(InventoryItem, "IC-0001")
        inv.price_cents = 12345
        session.commit()

    tools = {t.name: t for t in make_order_tools("cust-A", "conv-1")}
    prepared = json.loads(tools["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": 1}]}))
    assert prepared["items"][0]["unit_price_cents"] == 12345
    assert prepared["total_cents"] == 12345
