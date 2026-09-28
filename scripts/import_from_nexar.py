"""
Alternative to data/generate_synthetic_data.py and scripts/import_from_mouser.py:
populates data/catalog.json with REAL data aggregated across many
distributors (Digi-Key, Mouser, Farnell, Arrow, etc.) via the Nexar
(Octopart) Supply API.

Nexar's free tier is fully self-service: register an application at
https://portal.nexar.com/ (Applications -> New Application -> "supply.domain"
scope) to get a client_id/client_secret. No business-account approval and no
separate request form, unlike Mouser's Search API.

Produces the exact same catalog.json shape as the other importers, so
scripts/seed_demo_data.py and scripts/ingest_products.py run unmodified.

NOTE: Nexar's GraphQL schema isn't pinned here against a live test (no
credentials were available while writing this) — field names below are
based on Nexar's published docs/examples. If a query comes back empty or
errors, cross-check field names against the schema explorer at
https://api.nexar.com/ui/voyager.

Usage:
    python -m scripts.import_from_nexar
    python -m scripts.import_from_nexar --per-category 15
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from data.generate_synthetic_data import placeholder_image_url  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"

TOKEN_URL = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"

# Same category buckets as scripts/import_from_mouser.py, since supSearch is
# a general keyword search (not limited to exact MPN matches like
# supSearchMpn), these plain-language terms work directly.
CATEGORY_KEYWORDS = {
    "IC": "operational amplifier",
    "MCU": "microcontroller",
    "Motor": "DC motor",
    "Sensor": "temperature sensor",
    "Passive Component": "resistor",
    "Connector": "USB connector",
    "Power Supply Module": "DC-DC converter module",
}

SEARCH_QUERY = """
query ($q: String!, $limit: Int!) {
  supSearch(q: $q, limit: $limit, country: "US", currency: "USD") {
    hits
    results {
      part {
        mpn
        manufacturer { name }
        shortDescription
        specs { attribute { name } displayValue }
        images { url }
        sellers(authorizedOnly: true) {
          company { name }
          offers {
            inventoryLevel
            prices { quantity price currency }
          }
        }
      }
    }
  }
}
"""


def _get_access_token() -> str:
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.nexar_client_id,
            "client_secret": settings.nexar_client_secret,
            "scope": "supply.domain",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Nexar auth failed: HTTP {e.code} {e.reason} — check "
            f"NEXAR_CLIENT_ID/NEXAR_CLIENT_SECRET."
        ) from e

    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"Nexar auth response missing access_token: {payload}")
    return token


def _search_keyword(token: str, keyword: str, limit: int) -> list[dict]:
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(
            {"query": SEARCH_QUERY, "variables": {"q": keyword, "limit": limit}}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Nexar search for '{keyword}' failed: HTTP {e.code} {e.reason}"
        ) from e

    if payload.get("errors"):
        print(f"  Nexar API returned errors for '{keyword}': {payload['errors']}")

    data = payload.get("data") or {}
    return ((data.get("supSearch") or {}).get("results")) or []


def _cheapest_usd_price(sellers: list[dict]) -> float | None:
    best = None
    for seller in sellers or []:
        for offer in seller.get("offers") or []:
            for price_break in offer.get("prices") or []:
                if price_break.get("currency") not in (None, "USD"):
                    continue
                price = price_break.get("price")
                if price is None:
                    continue
                if best is None or price < best:
                    best = price
    return best


def _total_stock(sellers: list[dict]) -> int:
    return sum(
        offer.get("inventoryLevel") or 0
        for seller in (sellers or [])
        for offer in (seller.get("offers") or [])
    )


def _to_catalog_entry(result: dict, category: str) -> dict | None:
    part = result.get("part") or {}
    mpn = part.get("mpn")
    manufacturer = (part.get("manufacturer") or {}).get("name", "")
    description = part.get("shortDescription") or ""
    if not mpn or not description:
        return None

    sellers = part.get("sellers") or []
    price_usd = _cheapest_usd_price(sellers)
    if price_usd is None:
        # No USD pricing from any authorized seller — skip rather than
        # inventing a price for a real part.
        return None

    sku = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{manufacturer}-{mpn}").strip("-") or mpn

    specs = {
        spec["attribute"]["name"]: spec["displayValue"]
        for spec in (part.get("specs") or [])
        if spec.get("attribute", {}).get("name") and spec.get("displayValue")
    }
    if manufacturer:
        specs.setdefault("Manufacturer", manufacturer)

    images = part.get("images") or []
    image_url = (
        images[0]["url"]
        if images and images[0].get("url")
        else placeholder_image_url(sku, mpn, category)
    )

    return {
        "sku": sku,
        "name": mpn,
        "category": category,
        "description": f"{manufacturer} {mpn}: {description}".strip(": "),
        "specs": specs,
        "price_usd": round(price_usd, 4),
        "stock_level": _total_stock(sellers),
        "image_url": image_url,
        "source": "nexar_api",
    }


def fetch_catalog(per_category: int) -> list[dict]:
    token = _get_access_token()
    products: list[dict] = []
    seen_skus: set[str] = set()

    for category, keyword in CATEGORY_KEYWORDS.items():
        print(f"Searching Nexar for '{keyword}' ({category})...")
        results = _search_keyword(token, keyword, limit=per_category)
        added = 0
        for result in results:
            entry = _to_catalog_entry(result, category)
            if entry is None or entry["sku"] in seen_skus:
                continue
            seen_skus.add(entry["sku"])
            products.append(entry)
            added += 1
        print(f"  -> added {added} products")
        time.sleep(1)  # be polite to the free tier's rate limit

    return products


def save_catalog(products: list[dict]) -> None:
    with open(CATALOG_PATH, "w") as f:
        json.dump(products, f, indent=2)
    print(f"Saved {len(products)} products -> {CATALOG_PATH}")


def main():
    if not settings.nexar_client_id or not settings.nexar_client_secret:
        raise EnvironmentError(
            "NEXAR_CLIENT_ID / NEXAR_CLIENT_SECRET are not set. Register a free "
            "app at https://portal.nexar.com/ (supply.domain scope) and add "
            "them to .env."
        )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--per-category", type=int, default=10,
        help="Max parts to request per category keyword (default: 10)",
    )
    args = parser.parse_args()

    products = fetch_catalog(per_category=args.per_category)
    if not products:
        raise RuntimeError("No products imported — check Nexar credentials and try again.")

    save_catalog(products)

    print(
        "\nDone. Next steps:\n"
        "  python -m scripts.seed_demo_data\n"
        "  python -m scripts.ingest_products"
    )


if __name__ == "__main__":
    main()
