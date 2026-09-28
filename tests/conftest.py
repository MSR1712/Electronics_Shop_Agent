"""
Shared test fixtures. Uses a temp file-based SQLite DB per test (not
:memory:, since order_tools opens its own sessions via db.session.get_session
which needs a real file all threads/sessions can see) and monkeypatches
db.session's engine/SessionLocal to point at it.
"""

import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.models import Base, Customer, InventoryItem  # noqa: E402


@pytest.fixture()
def test_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    import db.session as session_module

    monkeypatch.setattr(session_module, "engine", engine)
    monkeypatch.setattr(session_module, "SessionLocal", SessionLocal)

    yield engine

    engine.dispose()
    Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture()
def seeded_customers(test_db):
    from db.session import get_session

    with get_session() as session:
        session.add(Customer(id="cust-A", name="Customer A"))
        session.add(Customer(id="cust-B", name="Customer B"))
        session.commit()
    return ["cust-A", "cust-B"]


@pytest.fixture()
def seeded_inventory(test_db):
    from db.session import get_session

    with get_session() as session:
        session.add(InventoryItem(sku="IC-0001", name="Test Chip", price_cents=199, stock_level=2))
        session.add(InventoryItem(sku="IC-0002", name="Low Stock Chip", price_cents=500, stock_level=1))
        session.commit()
    return ["IC-0001", "IC-0002"]
