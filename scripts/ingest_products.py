"""
Ingest data/catalog.json into Chroma. Safe to re-run (upserts by SKU).

Usage:
    python -m scripts.ingest_products
    python -m scripts.ingest_products --skip-existing   # resume after a
                                                          # rate/quota-limited
                                                          # run was cut off
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from rag.ingest import ingest_products  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip SKUs already embedded instead of re-embedding them",
    )
    args = parser.parse_args()
    ingest_products(skip_existing=args.skip_existing)
