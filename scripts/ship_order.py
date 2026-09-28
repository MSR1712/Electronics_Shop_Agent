"""
Admin CLI for the fulfillment workflow (tools/fulfillment_tools.py).

mark_processing/mark_shipped/mark_delivered are deliberately NOT agent
tools — the customer-facing chat agent must never decide an order
shipped; only a human/admin action does. This script is that action for
the demo, standing in for a real warehouse system's webhook or an
internal admin dashboard (same "no admin UI yet" gap this project's
README already flags for the return workflow).

Usage:
    python -m scripts.ship_order processing <order_id>
    python -m scripts.ship_order shipped <order_id> <tracking_number> [carrier]
    python -m scripts.ship_order delivered <order_id>
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.session import init_db  # noqa: E402
from tools.fulfillment_tools import mark_delivered, mark_processing, mark_shipped  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("processing", help="confirmed -> processing")
    p.add_argument("order_id", type=int)

    s = sub.add_parser("shipped", help="confirmed/processing -> shipped")
    s.add_argument("order_id", type=int)
    s.add_argument("tracking_number")
    s.add_argument("carrier", nargs="?", default=None)

    d = sub.add_parser("delivered", help="shipped -> delivered")
    d.add_argument("order_id", type=int)

    args = parser.parse_args()
    init_db()

    if args.action == "processing":
        result = mark_processing(args.order_id)
    elif args.action == "shipped":
        result = mark_shipped(args.order_id, args.tracking_number, args.carrier)
    else:
        result = mark_delivered(args.order_id)

    print(result)
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
