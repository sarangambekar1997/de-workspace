"""Rolling 7-day revenue report, run whenever the daily revenue table is updated.

Scheduled on an asset instead of a time: it runs after each successful
publish_daily_revenue task in shop_daily, however late or early that happens.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import duckdb
from airflow.sdk import Asset, dag, task

WAREHOUSE = Path(os.environ.get("LAB_WAREHOUSE_DIR", "/opt/lab/warehouse"))
DAILY_REVENUE = Asset("duckdb://shop/daily_revenue")


@dag(schedule=[DAILY_REVENUE], start_date=datetime(2024, 3, 1), catchup=False, tags=["lab05"])
def weekly_report():

    @task(pool="duckdb")
    def write_report() -> str:
        report = WAREHOUSE / "reports" / "revenue_last_7_days.csv"
        report.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(WAREHOUSE / "shop.duckdb"), read_only=True) as con:
            con.execute(f"""
                COPY (
                    SELECT order_date, orders, revenue,
                           round(avg(revenue) OVER (ORDER BY order_date ROWS 6 PRECEDING), 2) AS revenue_7d_avg
                    FROM daily_revenue
                    ORDER BY order_date DESC
                    LIMIT 7
                ) TO '{report}' (HEADER)
            """)
        print(f"Wrote {report}")
        return str(report)

    write_report()


weekly_report()
