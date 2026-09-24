"""Apply one day of source changes to the generated dataset.

Run after generate.py to see incremental models and snapshots react to new data:
    - appends a new day of orders, order items, and events (2024-03-31)
    - cancels one order from two days earlier (a late update to already-loaded data)
    - moves three customers to a new country (a slowly changing dimension)

Usage:
    python simulate_changes.py             # modifies ./output in place; run once
"""
from __future__ import annotations

import argparse
import csv
import tempfile
from datetime import date
from pathlib import Path

from generate import generate

NEW_DAY = date(2024, 3, 31)
CHANGED_AT = "2024-03-31T12:00:00Z"
MOVED_CUSTOMERS = {7: "JP", 42: "BR", 99: "DE"}


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "output")
    out = parser.parse_args().out

    orders = read_csv(out / "orders.csv")
    if any(o["order_ts"].startswith(NEW_DAY.isoformat()) for o in orders):
        print(f"Changes already applied to {out}; run generate.py to start over.")
        return

    # 1. A new day of data, generated separately and appended
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp), start=NEW_DAY, days=1)
        new_orders = read_csv(Path(tmp) / "orders.csv")
        new_items = read_csv(Path(tmp) / "order_items.csv")
        new_events = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8")

    # 2. A late update: cancel the first order placed two days before the new day
    late = next(o for o in orders if o["order_ts"].startswith("2024-03-29") and o["status"] == "paid")
    orders.append({**late, "status": "cancelled", "updated_at": CHANGED_AT})

    write_csv(out / "orders.csv", orders + new_orders)
    write_csv(out / "order_items.csv", read_csv(out / "order_items.csv") + new_items)
    with open(out / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(new_events)

    # 3. Customers who moved country
    customers = read_csv(out / "customers.csv")
    for c in customers:
        if int(c["customer_id"]) in MOVED_CUSTOMERS:
            c["country"] = MOVED_CUSTOMERS[int(c["customer_id"])]
            c["updated_at"] = CHANGED_AT
    write_csv(out / "customers.csv", customers)

    print(f"Applied changes to {out}")
    print(f"  appended   {len(new_orders):>5} orders for {NEW_DAY}")
    print(f"  cancelled  order {late['order_id']} (placed {late['order_ts'][:10]})")
    print(f"  moved      customers {', '.join(map(str, MOVED_CUSTOMERS))}")


if __name__ == "__main__":
    main()
