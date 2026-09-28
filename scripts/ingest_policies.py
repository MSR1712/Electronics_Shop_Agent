"""Ingest data/policies/*.md into Chroma. Safe to re-run (upserts by chunk id)."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from rag.ingest import ingest_policies  # noqa: E402

if __name__ == "__main__":
    ingest_policies()
