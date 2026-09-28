"""
⚠️  DESTROYS all data in the configured database (orders, inventory,
    customers, escalations) and recreates empty tables.

Usage:
    python -m scripts.reset_demo_db
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.models import Base  # noqa: E402
from db.session import engine  # noqa: E402


def main():
    confirm = input(
        "This will DROP ALL TABLES in the configured database. "
        "Type 'reset' to confirm: "
    )
    if confirm.strip().lower() != "reset":
        print("Aborted.")
        return

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Database reset. Run `python -m scripts.seed_demo_data` to repopulate demo data.")


if __name__ == "__main__":
    main()
