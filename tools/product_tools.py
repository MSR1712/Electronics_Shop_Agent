"""
Tools for the product-info agent.

ARCHITECTURE (Change 2): Chroma is a retrieval index over product
*identity and description* only — it does NOT store price or stock, and
never has (see rag/ingest.py). search_product_catalog uses Chroma purely
to find the relevant SKU(s), then joins against the SQL `inventory` table
for current price/stock on every call. This means price/stock in a tool
result are always fresh, even if Chroma hasn't been re-ingested — there is
no "stale Chroma price" to accidentally trust, because Chroma is never
asked for one.

NOTE ON DATA PROVENANCE: the catalog embedded in Chroma is LLM-generated
demo data (see data/generate_synthetic_data.py). Before production use,
build Chroma from a real product database's descriptions instead.
"""

import json

from langchain_core.tools import tool

from config import settings
from db.models import InventoryItem
from db.session import get_session
from rag.vectorstore import get_product_vectorstore

# Below this relevance score, a "match" is treated as noise rather than a
# real answer. Tune against your own embedding model/dataset.
MIN_RELEVANCE = 0.5


def _current_price_and_stock(sku: str) -> dict | None:
    """The ONLY place price/stock are read for a product — always SQL, never Chroma."""
    with get_session() as session:
        inv = session.get(InventoryItem, sku)
        if inv is None:
            return None
        return {"price_cents": inv.price_cents, "stock_level": inv.stock_level}


@tool
def search_product_catalog(query: str, k: int = 4) -> str:
    """
    Semantic search over the internal product catalog (ICs, MCUs, motors,
    sensors, etc.) to find matching products and their descriptions/specs.
    Current price and stock are always looked up fresh from the inventory
    database for every result — never taken from the search index itself.
    Each result includes an image_url (may be None) — if the customer asks
    to see a picture/photo of a product, embed it in your reply as Markdown:
    ![name](image_url). These are placeholder demo images, not real product
    photography.
    Returns structured JSON, or {"found": false} if nothing relevant
    enough was found — in that case, do NOT guess; try web_search_specs
    (for a genuinely out-of-catalog part) or ask the customer to clarify.
    """
    store = get_product_vectorstore()
    results = store.similarity_search_with_relevance_scores(query, k=k)
    relevant = [(doc, score) for doc, score in results if score >= MIN_RELEVANCE]

    if not relevant:
        return json.dumps({"found": False, "reason": "no results above relevance threshold"})

    products = []
    for doc, score in relevant:
        m = doc.metadata
        current = _current_price_and_stock(m["sku"])
        entry = {
            "sku": m["sku"],
            "name": m["name"],
            "category": m["category"],
            "description": doc.page_content,
            "image_url": m.get("image_url") or None,
            "relevance_score": round(score, 3),
        }
        if current is None:
            # Chroma knows about this SKU but SQL inventory doesn't (e.g.
            # discontinued, or a data sync gap) — surface that plainly
            # rather than inventing a price/stock number.
            entry["price_cents"] = None
            entry["stock_level"] = None
            entry["availability_note"] = "No current price/stock record found for this SKU."
        else:
            entry.update(current)
        products.append(entry)

    return json.dumps({"found": True, "products": products})


@tool
def web_search_specs(component_name: str) -> str:
    """
    Fallback web search for a component's specs. ONLY use this when
    search_product_catalog returns found=false. Any price mentioned in web
    results is NOT authoritative and must never be used to place an order —
    always tell the customer this is general/external info, not our
    current price.
    """
    if not settings.tavily_api_key:
        return json.dumps({"found": False, "reason": "web search not configured (missing TAVILY_API_KEY)"})

    from langchain_community.tools.tavily_search import TavilySearchResults

    search = TavilySearchResults(max_results=3, tavily_api_key=settings.tavily_api_key)
    results = search.invoke({"query": f"{component_name} datasheet specifications"})
    if not results:
        return json.dumps({"found": False, "reason": "no web results"})

    formatted = [{"content": r.get("content", ""), "url": r.get("url", "")} for r in results]
    return json.dumps(
        {
            "found": True,
            "source": "web",
            "results": formatted,
            "note": "External source — not our catalog. Any price/availability here is NOT "
            "authoritative and must not be used to place an order.",
        }
    )
