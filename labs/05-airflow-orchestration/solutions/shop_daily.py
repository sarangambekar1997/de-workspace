"""Daily e-commerce pipeline: extract -> load -> check quality -> publish.

One run processes one day (the run's logical date). Every task can be re-run for any day and
gives the same result, so retries, clears and backfills are safe.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
from airflow.sdk import Asset, Param, dag, task

DATA_DIR = Path(os.environ.get("LAB_DATA_DIR", "/opt/lab/data"))
WAREHOUSE = Path(os.environ.get("LAB_WAREHOUSE_DIR", "/opt/lab/warehouse"))
DB_PATH = WAREHOUSE / "shop.duckdb"
DAILY_REVENUE = Asset("duckdb://shop/daily_revenue")        # consumed by the weekly_report DAG

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id BIGINT, customer_id INTEGER, order_ts TIMESTAMP, status VARCHAR,
    currency VARCHAR, updated_at TIMESTAMP, order_date DATE);
CREATE TABLE IF NOT EXISTS order_items (
    order_id BIGINT, line_no INTEGER, product_id INTEGER, quantity INTEGER,
    unit_price DECIMAL(10, 2), order_date DATE);
CREATE TABLE IF NOT EXISTS daily_revenue (
    order_date DATE PRIMARY KEY, orders INTEGER, revenue DECIMAL(12, 2), loaded_at TIMESTAMP);
"""


@dag(
    schedule="@daily",
    start_date=datetime(2024, 3, 1),
    end_date=datetime(2024, 3, 31),
    catchup=False,                     # past days are loaded on purpose, with a backfill
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=15)},
    params={"orders_per_day": Param(200, type="integer", minimum=1, description="Orders to generate")},
    tags=["lab05"],
)
def shop_daily():

    @task
    def extract(ds: str, params: dict) -> str:
        """Land one day of source files in a folder named after the day (a date partition)."""
        sys.path.insert(0, str(DATA_DIR))
        from generate import generate                         # the lab's data generator

        landing = WAREHOUSE / "landing" / ds
        seed = int(ds.replace("-", ""))                       # different, but repeatable, data per day
        counts = generate(landing, datetime.fromisoformat(ds).date(), days=1,
                          orders_per_day=params["orders_per_day"], seed=seed)
        print(f"Landed {counts} in {landing}")
        return str(landing)

    @task(pool="duckdb")
    def load(landing: str, ds: str) -> None:
        """Replace the day's rows: delete, then insert, in one transaction. Re-runs never duplicate."""
        with duckdb.connect(str(DB_PATH)) as con:
            con.execute(SCHEMA)
            con.execute("BEGIN")
            con.execute("DELETE FROM order_items WHERE order_date = ?", [ds])
            con.execute("DELETE FROM orders WHERE order_date = ?", [ds])
            con.execute(f"""
                INSERT INTO orders
                SELECT order_id, customer_id, order_ts, lower(status), currency, updated_at, ?::DATE
                FROM read_csv('{landing}/orders.csv', header = true, auto_detect = true)
                QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY updated_at DESC) = 1
            """, [ds])
            con.execute(f"""
                INSERT INTO order_items
                SELECT order_id, line_no, product_id, quantity, unit_price, ?::DATE
                FROM read_csv('{landing}/order_items.csv', header = true, auto_detect = true)
            """, [ds])
            con.execute("COMMIT")
            n = con.execute("SELECT count(*) FROM orders WHERE order_date = ?", [ds]).fetchone()[0]
        print(f"Loaded {n} orders for {ds}")

    @task(pool="duckdb", retries=0)                            # a failed check will not fix itself
    def check_quality(ds: str) -> None:
        """Stop the pipeline before publishing if the day's data looks wrong."""
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            orders, distinct_orders, missing_customer = con.execute("""
                SELECT count(*), count(DISTINCT order_id), count(*) FILTER (WHERE customer_id IS NULL)
                FROM orders WHERE order_date = ?""", [ds]).fetchone()
            lines, bad_lines = con.execute("""
                SELECT count(*), count(*) FILTER (WHERE quantity <= 0 OR product_id NOT BETWEEN 1 AND 20)
                FROM order_items WHERE order_date = ?""", [ds]).fetchone()

        failures = []
        if orders < 100:
            failures.append(f"only {orders} orders (expected at least 100)")
        if orders != distinct_orders:
            failures.append(f"{orders - distinct_orders} duplicate order rows")
        if orders and missing_customer / orders > 0.05:
            failures.append(f"{missing_customer} orders without a customer")
        if lines and bad_lines / lines > 0.02:
            failures.append(f"{bad_lines} of {lines} order lines invalid")
        if failures:
            raise ValueError(f"Quality check failed for {ds}: " + "; ".join(failures))
        print(f"Quality OK for {ds}: {orders} orders, {bad_lines} invalid lines of {lines}")

    @task(pool="duckdb", outlets=[DAILY_REVENUE])
    def publish_daily_revenue(ds: str) -> None:
        """Upsert the day's revenue. Downstream DAGs scheduled on the asset run after this."""
        with duckdb.connect(str(DB_PATH)) as con:
            con.execute("""
                INSERT OR REPLACE INTO daily_revenue
                SELECT ?::DATE, count(DISTINCT o.order_id), sum(i.quantity * i.unit_price), now()
                FROM orders o JOIN order_items i USING (order_id)
                WHERE o.order_date = ? AND o.status != 'cancelled'
                  AND i.quantity > 0 AND i.product_id BETWEEN 1 AND 20
            """, [ds, ds])

    landing = extract()
    load(landing) >> check_quality() >> publish_daily_revenue()


shop_daily()
