"""
Seeds/resets DEMO data: a few demo Customer rows and the inventory table
from data/catalog.json.

⚠️  THIS IS DESTRUCTIVE FOR THE INVENTORY TABLE. It upserts inventory rows
    to match data/catalog.json exactly (price/stock overwritten). Do not
    run this against a database with real orders/stock you care about.

Usage:
    python -m scripts.seed_demo_data
"""

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.models import Customer, InventoryItem  # noqa: E402
from db.session import get_session, init_db  # noqa: E402

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"

DEMO_CUSTOMERS = [
    {"id": "cust-001", "name": "Alice Rivera", "email": "alice@example.com"},
    {"id": "cust-002", "name": "Ben Ostrowski", "email": "ben@example.com"},
    {"id": "cust-003", "name": "Priya Nair", "email": "priya@example.com"},
]


def seed_customers() -> None:
    with get_session() as session:
        for c in DEMO_CUSTOMERS:
            existing = session.get(Customer, c["id"])
            if existing is None:
                session.add(Customer(**c))
        session.commit()
    print(f"Seeded {len(DEMO_CUSTOMERS)} demo customers.")


def seed_inventory() -> None:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"{CATALOG_PATH} not found — run `python -m data.generate_synthetic_data` first."
        )

    with open(CATALOG_PATH) as f:
        products = json.load(f)

    with get_session() as session:
        for p in products:
            price_cents = round(p["price_usd"] * 100)
            existing = session.get(InventoryItem, p["sku"])
            if existing:
                existing.name = p["name"]
                existing.price_cents = price_cents
                existing.stock_level = p["stock_level"]
            else:
                session.add(
                    InventoryItem(
                        sku=p["sku"],
                        name=p["name"],
                        price_cents=price_cents,
                        stock_level=p["stock_level"],
                    )
                )
        session.commit()

    print(f"Seeded/updated {len(products)} inventory rows from {CATALOG_PATH}")


def main():
    print("WARNING: This resets demo inventory + customers. Do not run against production.")
    init_db()
    seed_customers()
    seed_inventory()


if __name__ == "__main__":
    main()
