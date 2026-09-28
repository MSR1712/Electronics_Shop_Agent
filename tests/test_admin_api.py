"""Tests for the admin panel API (api/routers/admin.py + api/admin_session.py)."""

import dataclasses
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parent.parent))

import api.admin_session as admin_session  # noqa: E402
from api.main import app  # noqa: E402
from api.session import SESSION_COOKIE_NAME, sign_session  # noqa: E402
from db.models import Escalation, InventoryItem, Order, OrderStatus  # noqa: E402
from db.session import get_session  # noqa: E402
from tools.order_tools import make_order_tools  # noqa: E402
from tools.return_tools import make_return_tools  # noqa: E402

ADMIN_PASSWORD = "test-admin-password"


@pytest.fixture()
def admin_enabled(monkeypatch):
    patched = dataclasses.replace(admin_session.settings, admin_password=ADMIN_PASSWORD)
    monkeypatch.setattr(admin_session, "settings", patched)


@pytest.fixture()
def client(test_db, admin_enabled):
    # Not used as a context manager, so the app lifespan (settings.validate(),
    # build_graph()) doesn't run — these tests don't touch the LLM graph.
    return TestClient(app)


@pytest.fixture()
def admin_client(client):
    assert client.post("/api/admin/login", json={"password": ADMIN_PASSWORD}).status_code == 200
    return client


def _create_confirmed_order(customer_id="cust-A", conversation_id="conv-1", quantity=1):
    tools = {t.name: t for t in make_order_tools(customer_id, conversation_id)}
    prepared = json.loads(tools["prepare_order"].invoke({"items": [{"sku": "IC-0001", "quantity": quantity}]}))
    confirmed = json.loads(tools["confirm_order"].invoke({"confirmation_id": prepared["confirmation_id"]}))
    assert confirmed["success"] is True
    return confirmed["order_id"]


# --- Auth ---------------------------------------------------------------------

def test_admin_endpoints_require_admin_login(client):
    assert client.get("/api/admin/orders").status_code == 401
    assert client.post("/api/admin/orders/1/deliver").status_code == 401


def test_wrong_password_is_rejected(client):
    assert client.post("/api/admin/login", json={"password": "nope"}).status_code == 401
    assert client.get("/api/admin/me").status_code == 401


def test_customer_session_cannot_access_admin(client, seeded_customers):
    client.cookies.set(SESSION_COOKIE_NAME, sign_session("cust-A", "conv-1"))
    assert client.get("/api/admin/orders").status_code == 401


def test_admin_disabled_when_password_unset(test_db, monkeypatch):
    patched = dataclasses.replace(admin_session.settings, admin_password="")
    monkeypatch.setattr(admin_session, "settings", patched)
    c = TestClient(app)
    assert c.post("/api/admin/login", json={"password": "anything"}).status_code == 503
    assert c.get("/api/admin/orders").status_code == 503


def test_changing_admin_password_invalidates_existing_session(admin_client, monkeypatch):
    assert admin_client.get("/api/admin/me").status_code == 200
    patched = dataclasses.replace(admin_session.settings, admin_password="rotated-password")
    monkeypatch.setattr(admin_session, "settings", patched)
    assert admin_client.get("/api/admin/me").status_code == 401


# --- Fulfillment --------------------------------------------------------------

def test_admin_can_ship_and_deliver_order(admin_client, seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()

    r = admin_client.post(f"/api/admin/orders/{order_id}/ship", json={"tracking_number": "1Z999", "carrier": "UPS"})
    assert r.status_code == 200
    assert admin_client.post(f"/api/admin/orders/{order_id}/deliver").status_code == 200

    detail = admin_client.get(f"/api/admin/orders/{order_id}").json()
    assert detail["status"] == "delivered"
    assert detail["tracking_number"] == "1Z999"
    assert detail["customer_name"] == "Customer A"
    assert detail["items"][0]["name"] == "Test Chip"


def test_invalid_fulfillment_transition_returns_400(admin_client, seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    r = admin_client.post(f"/api/admin/orders/{order_id}/deliver")
    assert r.status_code == 400
    assert "shipped" in r.json()["detail"]["error"]


def test_order_list_filters_by_status(admin_client, seeded_customers, seeded_inventory):
    first = _create_confirmed_order()
    _create_confirmed_order(conversation_id="conv-2")
    admin_client.post(f"/api/admin/orders/{first}/processing")

    orders = admin_client.get("/api/admin/orders", params={"status": "processing"}).json()["orders"]
    assert [o["order_id"] for o in orders] == [first]


# --- Returns ------------------------------------------------------------------

def test_admin_return_approve_then_refund_once(admin_client, seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    tools = {t.name: t for t in make_return_tools("cust-A")}
    return_id = json.loads(tools["request_return"].invoke({"order_id": order_id, "reason": "Wrong part"}))["return_id"]

    assert admin_client.post(f"/api/admin/returns/{return_id}/approve", json={"resolution": "OK"}).status_code == 200
    assert admin_client.post(f"/api/admin/returns/{return_id}/refund").status_code == 200
    second = admin_client.post(f"/api/admin/returns/{return_id}/refund")
    assert second.status_code == 400
    assert "already been refunded" in second.json()["detail"]["error"]

    with get_session() as session:
        assert session.get(Order, order_id).status == OrderStatus.REFUNDED


def test_admin_reject_return_restores_order_status(admin_client, seeded_customers, seeded_inventory):
    order_id = _create_confirmed_order()
    tools = {t.name: t for t in make_return_tools("cust-A")}
    return_id = json.loads(tools["request_return"].invoke({"order_id": order_id, "reason": "Changed mind"}))["return_id"]

    assert admin_client.post(f"/api/admin/returns/{return_id}/reject", json={}).status_code == 200
    with get_session() as session:
        assert session.get(Order, order_id).status == OrderStatus.CONFIRMED


# --- Escalations --------------------------------------------------------------

def test_admin_can_assign_and_resolve_escalation(admin_client, seeded_customers):
    with get_session() as session:
        esc = Escalation(customer_id="cust-A", reason="Board arrived damaged")
        session.add(esc)
        session.commit()
        esc_id = esc.id

    r = admin_client.patch(
        f"/api/admin/escalations/{esc_id}",
        json={"status": "resolved", "assigned_agent": "Sam", "resolution": "Sent replacement"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert admin_client.get("/api/admin/summary").json()["open_escalations"] == 0


def test_invalid_escalation_status_is_rejected(admin_client, seeded_customers):
    with get_session() as session:
        esc = Escalation(customer_id="cust-A", reason="x")
        session.add(esc)
        session.commit()
        esc_id = esc.id
    assert admin_client.patch(f"/api/admin/escalations/{esc_id}", json={"status": "bogus"}).status_code == 422


# --- Inventory ----------------------------------------------------------------

def test_admin_can_restock_and_reprice(admin_client, seeded_inventory):
    r = admin_client.patch("/api/admin/inventory/IC-0001", json={"stock_delta": 10, "price_cents": 250})
    assert r.status_code == 200
    assert r.json()["stock_level"] == 12
    assert r.json()["price_cents"] == 250


def test_stock_adjustment_cannot_go_negative(admin_client, seeded_inventory):
    r = admin_client.patch("/api/admin/inventory/IC-0002", json={"stock_delta": -5})
    assert r.status_code == 400
    with get_session() as session:
        assert session.get(InventoryItem, "IC-0002").stock_level == 1


def test_inventory_search_and_low_stock_filter(admin_client, seeded_inventory):
    res = admin_client.get("/api/admin/inventory", params={"q": "low stock"}).json()
    assert [i["sku"] for i in res["items"]] == ["IC-0002"]
    assert res["total"] == 1

    res = admin_client.get("/api/admin/inventory", params={"low_stock": "true", "limit": 1}).json()
    assert res["total"] == 2
    assert len(res["items"]) == 1
