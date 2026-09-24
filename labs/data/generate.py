"""Generate a deterministic e-commerce dataset for the labs.

Tables (CSV) and events (JSON Lines):
    customers.csv     customer_id, email, first_name, country, signup_date, updated_at
    products.csv      product_id, sku, name, category, unit_price
    orders.csv        order_id, customer_id, order_ts, status, currency, updated_at
    order_items.csv   order_id, line_no, product_id, quantity, unit_price
    events.jsonl      event_id, customer_id, event_type, page, event_ts, received_ts

The data deliberately contains realistic problems to find and fix:
    - orders that appear more than once (later versions with a new status and updated_at)
    - orders with a missing customer_id
    - a few negative line quantities (refund lines entered incorrectly)
    - order items referencing products that don't exist
    - inconsistent status casing ("SHIPPED" vs "shipped")
    - late-arriving events (received hours after they happened)
    - duplicate events (same event_id delivered twice)

Usage:
    python generate.py                                   # 30 days from 2024-03-01 into ./output
    python generate.py --start 2024-03-15 --days 1 --out /tmp/day   # a single day's orders
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

COUNTRIES = ["DE", "FR", "GB", "US", "US", "US", "IN", "BR", "JP", "ES"]
CATEGORIES = {
    "electronics": ["Headphones", "Keyboard", "Monitor", "Webcam", "Charger"],
    "home": ["Lamp", "Kettle", "Chair", "Rug", "Mug"],
    "books": ["Data Engineering Book", "SQL Handbook", "Python Guide", "Novel", "Cookbook"],
    "sports": ["Yoga Mat", "Dumbbells", "Water Bottle", "Running Socks", "Backpack"],
}
STATUSES = ["placed", "paid", "shipped", "delivered", "cancelled"]
FIRST_NAMES = ["Alex", "Sam", "Priya", "Chen", "Maria", "Jonas", "Aisha", "Luca", "Yuki", "Omar"]
PAGES = ["/", "/search", "/product", "/cart", "/checkout", "/account"]


def _ts(d: date, rng: random.Random) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(seconds=rng.randint(0, 86_399))


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(out_dir: Path, start: date, days: int, orders_per_day: int = 200,
             n_customers: int = 3000, seed: int = 42) -> dict[str, int]:
    """Write the dataset to out_dir and return row counts per file."""
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Products ──────────────────────────────────────────────────────────────
    products = []
    pid = 1
    for category, names in CATEGORIES.items():
        for name in names:
            products.append({
                "product_id": pid,
                "sku": f"{category[:3].upper()}-{pid:04d}",
                "name": name,
                "category": category,
                "unit_price": round(rng.uniform(5, 300), 2),
            })
            pid += 1
    price_by_id = {p["product_id"]: p["unit_price"] for p in products}

    # ── Customers (stable across runs thanks to the seed) ───────────────────────
    customers = []
    for cid in range(1, n_customers + 1):
        signup = date(2023, 1, 1) + timedelta(days=rng.randint(0, 400))
        customers.append({
            "customer_id": cid,
            "email": f"customer{cid}@example.com",
            "first_name": rng.choice(FIRST_NAMES),
            "country": rng.choice(COUNTRIES),
            "signup_date": signup.isoformat(),
            "updated_at": _iso(_ts(signup, rng)),
        })
    # A few customers moved country later (useful for SCD Type 2 exercises)
    for c in rng.sample(customers, 15):
        c["country"] = rng.choice(COUNTRIES)
        c["updated_at"] = _iso(_ts(start + timedelta(days=rng.randint(0, max(days - 1, 0))), rng))

    # ── Orders, items, and events ─────────────────────────────────────────────
    orders, items, events = [], [], []
    order_id = 1 + (start - date(2024, 1, 1)).days * 10_000     # unique across generated days
    event_id = order_id * 10
    for day_offset in range(days):
        d = start + timedelta(days=day_offset)
        for _ in range(orders_per_day):
            order_ts = _ts(d, rng)
            # Skewed demand: 20% of customers place most orders, many buy only once
            if rng.random() < 0.6:
                customer_id = rng.randint(1, max(1, n_customers // 5))
            else:
                customer_id = rng.randint(1, n_customers)
            status = rng.choices(STATUSES, weights=[10, 20, 30, 35, 5])[0]
            if rng.random() < 0.03:
                status = status.upper()                          # inconsistent casing
            orders.append({
                "order_id": order_id,
                "customer_id": "" if rng.random() < 0.01 else customer_id,   # missing FK
                "order_ts": _iso(order_ts),
                "status": status,
                "currency": rng.choice(["USD", "USD", "EUR", "GBP"]),
                "updated_at": _iso(order_ts),
            })
            if rng.random() < 0.05:                              # later version of the same order
                later = order_ts + timedelta(hours=rng.randint(1, 48))
                orders.append({**orders[-1], "status": "delivered", "updated_at": _iso(later)})

            for line_no in range(1, rng.randint(1, 4) + 1):
                product_id = rng.randint(1, len(products))
                if rng.random() < 0.005:
                    product_id = 999                             # orphan product
                quantity = rng.randint(1, 3)
                if rng.random() < 0.004:
                    quantity = -quantity                         # bad data
                items.append({
                    "order_id": order_id,
                    "line_no": line_no,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": price_by_id.get(product_id, 49.99),
                })

            # Clickstream leading up to the order
            for step, page in enumerate(["/", "/search", "/product", "/cart", "/checkout"]):
                event_ts = order_ts - timedelta(minutes=5 * (5 - step))
                delay = timedelta(hours=rng.randint(2, 30)) if rng.random() < 0.02 else timedelta(seconds=rng.randint(0, 5))
                event = {
                    "event_id": event_id,
                    "customer_id": customer_id,
                    "event_type": "page_view",
                    "page": page,
                    "event_ts": _iso(event_ts),
                    "received_ts": _iso(event_ts + delay),       # some events arrive late
                }
                events.append(event)
                if rng.random() < 0.01:
                    events.append(dict(event))                   # duplicate delivery
                event_id += 1
            order_id += 1

    def write_csv(name: str, rows: list[dict]) -> None:
        with open(out_dir / name, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    write_csv("customers.csv", customers)
    write_csv("products.csv", products)
    write_csv("orders.csv", orders)
    write_csv("order_items.csv", items)
    with open(out_dir / "events.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    return {"customers": len(customers), "products": len(products), "orders": len(orders),
            "order_items": len(items), "events": len(events)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "output")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 3, 1))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--orders-per-day", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    counts = generate(args.out, args.start, args.days, args.orders_per_day, seed=args.seed)
    print(f"Wrote dataset to {args.out}")
    for table, n in counts.items():
        print(f"  {table:<12} {n:>8,} rows")


if __name__ == "__main__":
    main()
