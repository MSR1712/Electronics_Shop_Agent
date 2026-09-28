"""
Read-only catalog endpoints. Reuses tools/product_tools.py rather than
re-deriving the SQL-price/Chroma-description split:

- A text `query` goes straight through search_product_catalog.invoke(...)
  (semantic search + its existing per-result SQL price/stock join).
- A plain listing / category filter reads identity+description metadata
  directly from the product Chroma collection (get_product_vectorstore),
  then joins current price/stock via _current_price_and_stock — the exact
  same helper search_product_catalog uses, imported rather than
  reimplemented, so price/stock authority never drifts from "SQL only".
"""

import json

from fastapi import APIRouter, HTTPException

from rag.vectorstore import get_product_vectorstore
from tools.product_tools import _current_price_and_stock, search_product_catalog

router = APIRouter(prefix="/api", tags=["catalog"])


def _listing_entry(sku: str, name: str, category: str, description: str, image_url: str | None) -> dict | None:
    current = _current_price_and_stock(sku)
    if current is None:
        # Chroma knows the SKU but SQL inventory doesn't (discontinued /
        # sync gap) — leave it out of listings rather than showing an
        # unpurchasable product with a fabricated price.
        return None
    return {
        "sku": sku,
        "name": name,
        "category": category,
        "description": description,
        "image_url": image_url,
        **current,
    }


@router.get("/products")
def list_products(query: str | None = None, category: str | None = None, limit: int = 24):
    if query:
        raw = search_product_catalog.invoke({"query": query, "k": limit})
        data = json.loads(raw)
        if not data.get("found"):
            return {"products": []}
        return {"products": data["products"]}

    store = get_product_vectorstore()
    where = {"category": category} if category else None
    got = store.get(where=where, limit=limit, include=["metadatas", "documents"])

    products = []
    for meta, doc in zip(got["metadatas"], got["documents"]):
        entry = _listing_entry(
            sku=meta["sku"],
            name=meta["name"],
            category=meta["category"],
            description=doc,
            image_url=meta.get("image_url") or None,
        )
        if entry is not None:
            products.append(entry)
    return {"products": products}


@router.get("/categories")
def list_categories():
    """Not in the original spec — added so the storefront's category nav
    doesn't have to fetch every product just to find distinct category
    values."""
    store = get_product_vectorstore()
    got = store.get(include=["metadatas"])
    categories = sorted({m["category"] for m in got["metadatas"] if m.get("category")})
    return {"categories": categories}


@router.get("/products/{sku}")
def product_detail(sku: str):
    store = get_product_vectorstore()
    got = store.get(where={"sku": sku}, include=["metadatas", "documents"])
    current = _current_price_and_stock(sku)

    if not got["ids"] and current is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if got["ids"]:
        meta = got["metadatas"][0]
        entry = {
            "sku": sku,
            "name": meta["name"],
            "category": meta["category"],
            "description": got["documents"][0],
            "image_url": meta.get("image_url") or None,
        }
    else:
        # In SQL inventory but never ingested into Chroma — show what we
        # have rather than 404ing a real, purchasable SKU.
        entry = {"sku": sku, "name": sku, "category": None, "description": None, "image_url": None}

    if current is None:
        entry["price_cents"] = None
        entry["stock_level"] = None
        entry["availability_note"] = "No current price/stock record found for this SKU."
    else:
        entry.update(current)

    return entry
