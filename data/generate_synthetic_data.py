"""
Generates a synthetic product catalog and company policy/FAQ documents
using the LLM, each in a single call. Run this once to populate:
  - data/catalog.json
  - data/policies/returns.md
  - data/policies/warranty.md
  - data/policies/shipping.md
  - data/policies/faq.md

Usage:
    python -m data.generate_synthetic_data
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field

# Allow running as `python -m data.generate_synthetic_data` from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from llm import get_llm  # noqa: E402

DATA_DIR = Path(__file__).parent
POLICIES_DIR = DATA_DIR / "policies"

CATEGORIES = [
    "IC",
    "MCU",
    "Motor",
    "Sensor",
    "Passive Component",
    "Connector",
    "Power Supply Module",
]

# This is a fictional demo shop with no real product photography, so
# image_url is a deterministic placeholder (placehold.co), never LLM-
# generated — an LLM cannot produce a real, resolvable image URL. Color-coded
# by category purely so the demo catalog is visually distinguishable.
CATEGORY_IMAGE_COLORS = {
    "IC": "1f2937/60a5fa",
    "MCU": "1e293b/34d399",
    "Motor": "292524/f97316",
    "Sensor": "1e1b4b/a78bfa",
    "Passive Component": "27272a/facc15",
    "Connector": "18181b/f472b6",
    "Power Supply Module": "1c1917/fb7185",
}
DEFAULT_IMAGE_COLORS = "27272a/e4e4e7"

# Used to assign SKUs programmatically instead of asking the LLM to invent
# one per product — saves output tokens and guarantees no collisions across
# batches (see save_catalog's counter logic).
CATEGORY_SKU_PREFIX = {
    "IC": "IC",
    "MCU": "MCU",
    "Motor": "MTR",
    "Sensor": "SNS",
    "Passive Component": "PSV",
    "Connector": "CON",
    "Power Supply Module": "PSU",
}


def placeholder_image_url(sku: str, name: str, category: str) -> str:
    colors = CATEGORY_IMAGE_COLORS.get(category, DEFAULT_IMAGE_COLORS)
    text = quote(f"{name}\n{sku}")
    return f"https://placehold.co/600x400/{colors}?text={text}&font=roboto"


# ---------------------------------------------------------------------------
# Structured schema for the catalog — used with .with_structured_output()
# so Gemini returns valid, parseable JSON directly instead of us regex-ing
# a text blob out of a chat response.
# ---------------------------------------------------------------------------

class Product(BaseModel):
    name: str = Field(description="Product name, e.g. 'ATmega328P-PU'")
    category: str = Field(description=f"One of: {', '.join(CATEGORIES)}")
    description: str = Field(
        description="ONE concise sentence for semantic search — what it's used "
        "for and its single most distinguishing trait. No filler."
    )
    specs: dict[str, str] = Field(
        description="The 2-4 MOST relevant spec fields as short strings (e.g. "
        "voltage, package, interface) — not exhaustive, keep each value short."
    )
    price_usd: float = Field(description="Price in USD, realistic for the component type")
    stock_level: int = Field(description="Units currently in stock, integer 0-500")


class Catalog(BaseModel):
    products: list[Product]


class PolicyDocs(BaseModel):
    returns_policy_md: str = Field(description="Full returns policy as Markdown")
    warranty_policy_md: str = Field(description="Full warranty policy as Markdown")
    shipping_policy_md: str = Field(description="Full shipping policy as Markdown")
    faq_md: str = Field(description="8-12 common customer FAQs with answers, as Markdown")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_catalog(n_products: int = 40, categories: list[str] = CATEGORIES) -> Catalog:
    """Generates a synthetic catalog in a single structured-output call, spread
    across the given categories (defaults to all of them)."""
    llm = get_llm(temperature=0.7)
    structured_llm = llm.with_structured_output(Catalog)

    prompt = f"""Generate a synthetic product catalog for an electronics/robotics
component shop called "CircuitWorks".

Requirements:
- Exactly {n_products} products total, spread roughly evenly across these
  categories: {', '.join(categories)}.
- Use realistic, plausible part names and specs (you can invent part numbers
  in the style of real manufacturers, e.g. "STM32F103C8T6"-style, but do not
  claim to be an official manufacturer database — these are for a demo shop).
- Vary stock levels realistically: most items well-stocked, a few low stock
  (1-5 units), a few out of stock (0 units).
- Prices should be realistic for each component type (cents to a few dollars
  for passives/ICs, tens of dollars for motors/modules).
- Keep descriptions to ONE short sentence and specs to the 2-4 most relevant
  fields — brevity matters here, this is a bulk generation run.

Return only the structured data."""

    print(f"Generating {n_products}-product synthetic catalog...")
    catalog = structured_llm.invoke(prompt)
    return catalog


def generate_policy_docs() -> PolicyDocs:
    """Generates returns/warranty/shipping policy + FAQ docs in a single call."""
    llm = get_llm(temperature=0.6)
    structured_llm = llm.with_structured_output(PolicyDocs)

    prompt = """Generate company policy documents for a fictional electronics/robotics
component shop called "CircuitWorks".

Write four separate Markdown documents:
1. Returns policy — return window, condition requirements, restocking fees
   (if any), what's non-returnable (e.g. cut reels, custom orders).
2. Warranty policy — warranty length by product category (electronics vs.
   mechanical parts like motors), what voids the warranty, RMA process.
3. Shipping policy — domestic/international shipping options, processing
   time, shipping cost tiers, what happens with backordered items.
4. FAQ — 8 to 12 realistic customer questions with concise answers, covering
   a mix of order status, product compatibility, bulk/wholesale pricing,
   and account questions.

Keep the tone professional but approachable, like a real small-to-mid-size
component retailer's help center. Use Markdown headers and bullet points.

Return only the structured data."""

    print("Generating policy documents...")
    docs = structured_llm.invoke(prompt)
    return docs


def _next_sku_counters(existing: list[dict]) -> dict[str, int]:
    """Highest existing numeric suffix per SKU prefix, so newly assigned SKUs
    keep counting up rather than colliding with what's already saved."""
    counters: dict[str, int] = {}
    for p in existing:
        prefix, _, suffix = p.get("sku", "").rpartition("-")
        if prefix and suffix.isdigit():
            counters[prefix] = max(counters.get(prefix, 0), int(suffix))
    return counters


def save_catalog(catalog: Catalog, merge: bool = False) -> None:
    """
    By default overwrites data/catalog.json entirely. With merge=True,
    appends to whatever's already there instead — used both to fill in
    categories missing from a real-data import (see
    scripts/import_from_mouser.py / scripts/import_from_nexar.py) and to
    accumulate multiple LLM batches for a large --count run without earlier
    batches being wiped by later ones.

    SKUs are assigned here (not by the LLM) — a running counter per category
    prefix, continuing from whatever's already in the file, so bulk runs
    can't produce colliding SKUs across batches.
    """
    out_path = DATA_DIR / "catalog.json"

    existing = []
    if merge and out_path.exists():
        with open(out_path) as f:
            existing = json.load(f)
    counters = _next_sku_counters(existing)

    new_products = []
    for p in catalog.products:
        prefix = CATEGORY_SKU_PREFIX.get(p.category, "SKU")
        counters[prefix] = counters.get(prefix, 0) + 1
        sku = f"{prefix}-{counters[prefix]:05d}"

        d = p.model_dump()
        d["sku"] = sku
        d["image_url"] = placeholder_image_url(sku, p.name, p.category)
        d.setdefault("source", "demo_synthetic_catalog")
        new_products.append(d)

    products = existing + new_products
    with open(out_path, "w") as f:
        json.dump(products, f, indent=2)
    print(f"Saved {len(new_products)} new products (total {len(products)}) -> {out_path}")


def save_policy_docs(docs: PolicyDocs) -> None:
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "returns.md": docs.returns_policy_md,
        "warranty.md": docs.warranty_policy_md,
        "shipping.md": docs.shipping_policy_md,
        "faq.md": docs.faq_md,
    }
    for filename, content in files.items():
        path = POLICIES_DIR / filename
        path.write_text(content)
        print(f"Saved -> {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--categories", type=str, default=None,
        help=f"Comma-separated subset of categories to generate (default: all). "
             f"One of: {', '.join(CATEGORIES)}",
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="Total products to generate (default: 40 for all categories, "
             "or 6 per selected category)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Products per LLM call (default: 50). --count values larger than "
             "this are automatically split across multiple calls, since a "
             "single call can't reliably return hundreds of items without "
             "truncation. Each batch is saved immediately, so an interrupted "
             "run keeps everything generated so far.",
    )
    parser.add_argument(
        "--merge", action="store_true",
        help="Append to the existing data/catalog.json instead of overwriting it "
             "(use this to fill in categories missing from a real-data import)",
    )
    parser.add_argument(
        "--skip-policies", action="store_true",
        help="Don't regenerate policy docs (useful when only filling in catalog gaps)",
    )
    args = parser.parse_args()

    categories = args.categories.split(",") if args.categories else CATEGORIES
    n_products = args.count or (40 if categories == CATEGORIES else 6 * len(categories))

    settings.validate()

    remaining = n_products
    merge = args.merge
    batch_num = 0
    while remaining > 0:
        batch_num += 1
        batch_n = min(args.batch_size, remaining)
        print(f"--- Batch {batch_num}: {batch_n} products "
              f"({n_products - remaining}/{n_products} done so far) ---")
        catalog = generate_catalog(n_products=batch_n, categories=categories)
        save_catalog(catalog, merge=merge)
        merge = True  # every batch after the first must append, not overwrite
        remaining -= batch_n
        if remaining > 0:
            time.sleep(1)  # be gentle on rate limits between calls

    if not args.skip_policies:
        docs = generate_policy_docs()
        save_policy_docs(docs)

    print("\nDone. Next step: run `python -m rag.ingest` to embed this "
          "data into Chroma.")


if __name__ == "__main__":
    main()
