"""
Alternative to data/generate_synthetic_data.py: populates data/catalog.json
with REAL distributor data from the Mouser Electronics Search API instead of
LLM-generated synthetic products.

Produces the exact same catalog.json shape (sku, name, category, description,
specs, price_usd, stock_level, image_url), so nothing downstream changes —
scripts/seed_demo_data.py (SQL price/stock) and scripts/ingest_products.py
(Chroma descriptions) run unmodified afterward.

Requires a free API key from https://www.mouser.com/api-search/, set as
MOUSER_API_KEY in .env.

RATE LIMITS (Mouser's published caps for a self-service Search API key):
  30 requests/minute, 1,000 requests/day. `--max-requests` defaults to a
  conservative 100 so a normal run leaves headroom for re-runs the same
  day; pass a higher value (up to 1000) deliberately if you want one run
  to use most/all of the daily budget. RATE_LIMIT_INTERVAL_SECONDS below
  paces requests at ~28/minute, under the 30/minute cap with margin for
  clock jitter.

Usage:
    python -m scripts.import_from_mouser
    python -m scripts.import_from_mouser --max-requests 1000
    python -m scripts.import_from_mouser --max-requests 1000 --records-per-request 50
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from data.generate_synthetic_data import placeholder_image_url  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
# Progress checkpoint — written after every successful request so a crash
# (network blip, Ctrl+C, killed process) never loses fetched products, and a
# later run resumes from these offsets instead of re-spending quota on pages
# already paid for. Deleted once every category is exhausted.
CHECKPOINT_PATH = DATA_DIR / ".mouser_import_checkpoint.json"

SEARCH_URL = "https://api.mouser.com/api/v1/search/keyword"

# 60s / 28 requests ≈ 2.14s between calls — stays under Mouser's documented
# 30/minute cap with margin, rather than pacing right up against it.
RATE_LIMIT_INTERVAL_SECONDS = 60 / 28
DAILY_REQUEST_CAP = 1000

# Our own category buckets, each mapped to a Mouser keyword search likely to
# return relevant parts. Mouser's own free-text "Category" field is too
# inconsistent to bucket on directly, so we tag results with the bucket we
# searched under instead.
CATEGORY_KEYWORDS = {
    "IC": "operational amplifier",
    "MCU": "microcontroller",
    "Motor": "DC motor",
    "Sensor": "temperature sensor",
    "Passive Component": "resistor",
    "Connector": "USB connector",
    "Power Supply Module": "DC-DC converter module",
}


_last_request_time: float = 0.0


def _rate_limit() -> None:
    """Blocks just long enough to keep calls under Mouser's 30/minute cap
    (see RATE_LIMIT_INTERVAL_SECONDS) — called once per request, right
    before it goes out, so the budget is paced regardless of which
    category/page it's for."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < RATE_LIMIT_INTERVAL_SECONDS:
        time.sleep(RATE_LIMIT_INTERVAL_SECONDS - elapsed)
    _last_request_time = time.monotonic()


RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def _search_keyword(keyword: str, records: int, starting_record: int = 0) -> list[dict]:
    """A single page over the open internet, run up to MAX_ATTEMPTS times.
    Timeouts/connection errors and 429/5xx responses are transient — worth
    retrying with backoff rather than aborting a 30+ minute run over one
    blip. Anything else (bad request, auth failure, ...) is not transient
    and raises immediately on the first attempt."""
    body = json.dumps(
        {
            "SearchByKeywordRequest": {
                "keyword": keyword,
                "records": records,
                "startingRecord": starting_record,
                "searchOptions": "",
                "searchWithYourSignUpLanguage": "false",
            }
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{SEARCH_URL}?apiKey={settings.mouser_api_key}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_HTTP_STATUSES or attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Mouser API request for '{keyword}' (offset {starting_record}) failed: "
                    f"HTTP {e.code} {e.reason}"
                ) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Mouser API request for '{keyword}' (offset {starting_record}) failed "
                    f"after {MAX_ATTEMPTS} attempts: {e}"
                ) from e
        # Only reached when an exception was caught above but not raised
        # (a retryable failure on a non-final attempt) — the success path's
        # `break` above exits the loop before ever reaching this line.
        wait = 2 * attempt
        print(f"  [warn] '{keyword}' offset={starting_record} attempt {attempt}/{MAX_ATTEMPTS} failed — retrying in {wait}s")
        time.sleep(wait)

    errors = payload.get("Errors") or []
    if errors:
        print(f"  Mouser API returned errors for '{keyword}': {errors}")

    return (payload.get("SearchResults") or {}).get("Parts") or []


def _parse_price_usd(price_breaks: list[dict]) -> float | None:
    if not price_breaks:
        return None
    raw = price_breaks[0].get("Price", "")
    cleaned = re.sub(r"[^0-9.]", "", raw)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_stock_level(part: dict) -> int:
    raw = part.get("AvailabilityInStock") or part.get("Availability") or ""
    match = re.match(r"\s*([\d,]+)", raw)
    return int(match.group(1).replace(",", "")) if match else 0


def _to_catalog_entry(part: dict, category: str) -> dict | None:
    sku = part.get("MouserPartNumber")
    mfr_part = part.get("ManufacturerPartNumber")
    manufacturer = part.get("Manufacturer", "")
    description = part.get("Description", "")
    if not sku or not mfr_part or not description:
        return None

    price_usd = _parse_price_usd(part.get("PriceBreaks") or [])
    if price_usd is None:
        # No pricing available for this part on this account tier — skip
        # rather than inventing a price for a real distributor SKU.
        return None

    specs = {
        attr["AttributeName"]: attr["AttributeValue"]
        for attr in (part.get("ProductAttributes") or [])
        if attr.get("AttributeName") and attr.get("AttributeValue")
    }
    if manufacturer:
        specs.setdefault("Manufacturer", manufacturer)
    if part.get("ROHSStatus"):
        specs.setdefault("RoHS Status", part["ROHSStatus"])

    image_url = part.get("ImagePath") or placeholder_image_url(sku, mfr_part, category)

    return {
        "sku": sku,
        "name": mfr_part,
        "category": category,
        "description": f"{manufacturer} {mfr_part}: {description}".strip(": "),
        "specs": specs,
        "price_usd": price_usd,
        "stock_level": _parse_stock_level(part),
        "image_url": image_url,
        "source": "mouser_api",
    }


def _load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            return json.load(f)
    return {"offsets": {}, "exhausted": [], "seen_skus": [], "products": []}


def _save_checkpoint(offsets: dict, exhausted: set, seen_skus: set, products: list) -> None:
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(
            {
                "offsets": offsets,
                "exhausted": sorted(exhausted),
                "seen_skus": sorted(seen_skus),
                "products": products,
            },
            f,
        )


def fetch_catalog(max_requests: int, records_per_request: int) -> list[dict]:
    """Round-robins one page (one request) per category per pass, paging
    each category forward with `startingRecord` until either it runs out
    of results or the `max_requests` budget is spent — so a large budget
    fans out across all categories instead of exhausting itself on the
    first keyword before reaching the rest.

    Resumable by construction: progress is checkpointed to disk after
    every single request (see _save_checkpoint), and reloaded at startup
    if present — so a crash (network blip that exhausts _search_keyword's
    retries, Ctrl+C, killed process) never loses fetched products or
    forces re-spending quota on pages already paid for. The checkpoint is
    deleted once every category is genuinely exhausted."""
    checkpoint = _load_checkpoint()
    offsets = {**{category: 0 for category in CATEGORY_KEYWORDS}, **checkpoint["offsets"]}
    exhausted: set[str] = set(checkpoint["exhausted"])
    seen_skus: set[str] = set(checkpoint["seen_skus"])
    products: list[dict] = list(checkpoint["products"])
    requests_made = 0

    if products:
        print(f"Resuming from checkpoint: {len(products)} products already fetched, offsets={offsets}")

    try:
        while requests_made < max_requests and len(exhausted) < len(CATEGORY_KEYWORDS):
            for category, keyword in CATEGORY_KEYWORDS.items():
                if requests_made >= max_requests:
                    break
                if category in exhausted:
                    continue

                _rate_limit()
                offset = offsets[category]
                parts = _search_keyword(keyword, records=records_per_request, starting_record=offset)
                requests_made += 1
                print(
                    f"[{requests_made}/{max_requests}] '{keyword}' ({category}) "
                    f"offset={offset} -> {len(parts)} results"
                )

                if not parts:
                    exhausted.add(category)
                    _save_checkpoint(offsets, exhausted, seen_skus, products)
                    continue
                offsets[category] = offset + len(parts)
                if len(parts) < records_per_request:
                    # Short page — Mouser has no more results for this keyword.
                    exhausted.add(category)

                added = 0
                for part in parts:
                    entry = _to_catalog_entry(part, category)
                    if entry is None or entry["sku"] in seen_skus:
                        continue
                    seen_skus.add(entry["sku"])
                    products.append(entry)
                    added += 1
                print(f"  -> added {added} new products (total so far: {len(products)})")
                _save_checkpoint(offsets, exhausted, seen_skus, products)
    except KeyboardInterrupt:
        # Already checkpointed after the last completed request above —
        # this is just for an accurate console message.
        print(f"\nInterrupted after {requests_made} requests this run — keeping {len(products)} products total.")
    except Exception as e:
        # Any non-retryable failure (retries exhausted in _search_keyword,
        # or anything else unexpected): the checkpoint written after the
        # last successful request already has everything up to that point
        # safely on disk — don't lose it by letting this propagate.
        print(f"\n[error] {e}\nStopping — keeping {len(products)} products fetched so far (checkpoint saved).")

    if len(exhausted) >= len(CATEGORY_KEYWORDS):
        # Nothing left to resume — the checkpoint would only cause a next
        # run to immediately report "all exhausted" for no benefit.
        CHECKPOINT_PATH.unlink(missing_ok=True)
        print("All categories exhausted — checkpoint cleared.")

    return products


def save_catalog(products: list[dict]) -> None:
    with open(CATALOG_PATH, "w") as f:
        json.dump(products, f, indent=2)
    print(f"Saved {len(products)} products -> {CATALOG_PATH}")


def main():
    if not settings.mouser_api_key:
        raise EnvironmentError(
            "MOUSER_API_KEY is not set. Get a free key at "
            "https://www.mouser.com/api-search/ and add it to .env."
        )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-requests", type=int, default=100,
        help=(
            "Total Mouser API requests to spend on this run (default: 100). "
            f"Mouser's daily cap is {DAILY_REQUEST_CAP} — pass up to that to "
            "pull a much larger catalog in one run, but leave 0 room for "
            "re-runs the same day if you do."
        ),
    )
    parser.add_argument(
        "--records-per-request", type=int, default=50,
        help="Parts requested per page/request (default: 50, Mouser's typical max page size)",
    )
    args = parser.parse_args()

    if args.max_requests > DAILY_REQUEST_CAP:
        raise ValueError(
            f"--max-requests {args.max_requests} exceeds Mouser's documented "
            f"daily cap of {DAILY_REQUEST_CAP} requests for a Search API key."
        )

    products = fetch_catalog(
        max_requests=args.max_requests,
        records_per_request=args.records_per_request,
    )
    if not products:
        raise RuntimeError("No products imported — check MOUSER_API_KEY and try again.")

    save_catalog(products)

    print(
        "\nDone. Next steps:\n"
        "  python -m scripts.seed_demo_data\n"
        "  python -m scripts.ingest_products"
    )


if __name__ == "__main__":
    main()
