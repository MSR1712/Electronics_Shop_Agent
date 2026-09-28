"""
Embeds data/catalog.json and data/policies/*.md into their respective
Chroma collections, using explicit upsert semantics (delete-then-add by ID)
so re-running ingestion updates existing entries instead of erroring or
silently duplicating them.

NOTE ON SOURCE OF TRUTH: this reads price/stock from data/catalog.json
purely to embed a searchable description. The SQL `inventory` table
(db/models.py), seeded separately by scripts/seed_demo_data.py, is what
tools/order_tools.py actually reads for price and stock at transaction
time — Chroma metadata here is a cached snapshot for display/search
convenience, not authoritative.

Run via:
    python -m scripts.ingest_products
    python -m scripts.ingest_policies
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document  # noqa: E402
from langchain_text_splitters import MarkdownTextSplitter  # noqa: E402

from rag.vectorstore import get_policy_vectorstore, get_product_vectorstore  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
POLICIES_DIR = DATA_DIR / "policies"


CHUNK_SIZE = 40  # keeps each add_documents call comfortably under Google's
                  # free-tier embedding rate limit (100 requests/minute)


def _add_with_retry(store, docs: list[Document], ids: list[str], max_retries: int = 6) -> None:
    """
    A catalog of hundreds of products can exceed the free embedding tier's
    requests/minute limit mid-ingest. Retry with the server-suggested
    backoff (parsed from the 429's retryDelay) instead of failing the whole
    run partway through.
    """
    for attempt in range(max_retries):
        try:
            store.add_documents(docs, ids=ids)
            return
        except Exception as e:
            msg = str(e)
            if "RESOURCE_EXHAUSTED" not in msg and "429" not in msg:
                raise
            match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", msg)
            delay = int(match.group(1)) + 3 if match else 30
            print(f"  Rate limited by embedding API, retrying in {delay}s "
                  f"(attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
    raise RuntimeError("Gave up after repeated embedding rate-limit errors.")


def _upsert(store, docs: list[Document], ids: list[str]) -> None:
    """
    Chroma's add_documents raises/duplicates on IDs that already exist
    depending on version, so we make the upsert explicit: delete any
    existing rows with these IDs first, then add — in chunks small enough
    to stay under the embedding API's free-tier rate limit, with retry on
    429s so a large catalog doesn't fail partway through.
    """
    total = len(ids)
    for i in range(0, total, CHUNK_SIZE):
        doc_chunk = docs[i : i + CHUNK_SIZE]
        id_chunk = ids[i : i + CHUNK_SIZE]

        existing = store.get(ids=id_chunk)
        if existing and existing.get("ids"):
            store.delete(ids=existing["ids"])

        _add_with_retry(store, doc_chunk, id_chunk)
        print(f"  Embedded {min(i + CHUNK_SIZE, total)}/{total}")


def ingest_products(skip_existing: bool = False) -> None:
    """
    skip_existing=True skips SKUs already present in the collection instead
    of re-embedding them — for resuming a large ingest after it was cut off
    by the embedding API's rate/quota limit, without re-spending quota on
    products already embedded. Normal runs should leave this False, since
    catalog content (price/stock aside) can legitimately change and the
    default upsert semantics are meant to refresh it.
    """
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"{CATALOG_PATH} not found — run `python -m data.generate_synthetic_data` "
            f"(or point this at a real catalog export) first."
        )

    with open(CATALOG_PATH) as f:
        products = json.load(f)

    store = get_product_vectorstore()

    if skip_existing:
        all_skus = [p["sku"] for p in products]
        existing_skus = set()
        for i in range(0, len(all_skus), 200):
            batch = store.get(ids=all_skus[i : i + 200])
            existing_skus.update(batch.get("ids") or [])
        before = len(products)
        products = [p for p in products if p["sku"] not in existing_skus]
        print(f"Skipping {before - len(products)} already-embedded products, "
              f"{len(products)} remaining")

    now = datetime.now(timezone.utc).isoformat()
    docs, ids = [], []
    for p in products:
        specs_str = ", ".join(f"{k}: {v}" for k, v in p["specs"].items())
        page_content = (
            f"{p['name']} ({p['category']})\n"
            f"{p['description']}\n"
            f"Specs: {specs_str}"
        )
        # Deliberately NOT storing price_cents/stock_level here. Chroma is
        # a retrieval index over identity + description; price and stock
        # are looked up fresh from the SQL `inventory` table at query time
        # (see tools/product_tools.py) so they can never go stale relative
        # to what's actually orderable.
        docs.append(
            Document(
                page_content=page_content,
                metadata={
                    "sku": p["sku"],
                    "name": p["name"],
                    "category": p["category"],
                    "image_url": p.get("image_url", ""),
                    "source": p.get("source", "demo_synthetic_catalog"),
                    "updated_at": now,
                },
            )
        )
        ids.append(p["sku"])

    _upsert(store, docs, ids)
    print(f"Upserted {len(docs)} products into '{store._collection.name}'")


def ingest_policies() -> None:
    if not POLICIES_DIR.exists() or not any(POLICIES_DIR.glob("*.md")):
        raise FileNotFoundError(
            f"No .md files found in {POLICIES_DIR} — run "
            f"`python -m data.generate_synthetic_data` (or drop in real policy "
            f"docs) first."
        )

    splitter = MarkdownTextSplitter(chunk_size=800, chunk_overlap=100)
    now = datetime.now(timezone.utc).isoformat()
    docs, ids = [], []

    for path in sorted(POLICIES_DIR.glob("*.md")):
        text = path.read_text()
        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source": path.stem,
                        "chunk_index": i,
                        "updated_at": now,
                    },
                )
            )
            ids.append(f"{path.stem}-{i}")

    store = get_policy_vectorstore()
    _upsert(store, docs, ids)
    print(f"Upserted {len(docs)} policy chunks into '{store._collection.name}'")
