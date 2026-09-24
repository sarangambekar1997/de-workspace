# Lab 01 — SQL Analytics with DuckDB

Answer business and data quality questions with SQL over a realistic e-commerce dataset — including the duplicates, missing keys, bad values, and late events you meet in real pipelines.

| | |
|-|-|
| **Time** | 60–90 minutes |
| **Runs on** | Python + DuckDB (no Docker, no server) |
| **Guides** | [SQL](../../docs/00-foundations/sql-reference.md) · [DuckDB & Polars](../../docs/02-processing/duckdb-polars.md) · [Data Quality](../../docs/05-quality-governance/data-quality.md) |

## Setup

```bash
cd labs/01-sql-analytics
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python ../data/generate.py          # writes ../data/output/*.csv and events.jsonl
python run_sql.py setup.sql         # creates typed views over the files; prints row counts
```

## Data

| View | Grain | Notes |
|------|-------|-------|
| `customers` | One row per customer | Some customers changed country during the month |
| `products` | One row per product | 20 products in 4 categories |
| `raw_orders` | One row per order *version* | Some orders appear twice (a later status update); statuses have inconsistent casing; a few are missing `customer_id` |
| `order_items` | One row per order line | A few negative quantities and unknown `product_id`s |
| `events` | One row per page view *delivery* | Some events are delivered twice; some arrive hours late |

## Exercises

Write your answers in [`exercises.sql`](exercises.sql), then run `python run_sql.py exercises.sql`. Reference answers are in [`solutions.sql`](solutions.sql) — compare after each attempt.

| # | Task | Concepts | Hint |
|---|------|----------|------|
| 1 | Deduplicate orders into an `orders` view | Window functions, `QUALIFY` | `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC)` |
| 2 | Data quality report | Anti-joins, `COUNT` vs `COUNT DISTINCT` | Unknown products: `LEFT JOIN ... WHERE p.product_id IS NULL` |
| 3 | Daily revenue from clean lines | Joins, filtering bad data | Build a reusable `order_lines_clean` view first |
| 4 | Top 3 products per category | `RANK()` over an aggregate | You can rank by `SUM(...)` inside the window's `ORDER BY` |
| 5 | Lifetime value and repeat rate | CTEs, `FILTER` | Aggregate per customer first, then across customers |
| 6 | 7-day moving average | Window frames | `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` |
| 7 | Revenue by country | Dimension joins | Which country is used — the current one or the one at order time? |
| 8 | Checkout funnel | Conditional aggregation | `COUNT(DISTINCT customer_id) FILTER (WHERE page = '/cart')` |
| 9 | Late-arriving events | Interval arithmetic | `received_ts - event_ts > INTERVAL 1 HOUR` |
| 10 | Sessionization | `LAG` + running `SUM` | Flag a new session when the gap exceeds 30 minutes, then cumulatively sum the flags |

## Going further

- Q7 uses each customer's **current** country. How would you report revenue by the country the customer lived in **when they ordered**? (See SCD Type 2 in [Data Modeling](../../docs/01-storage/data-modeling.md) — Lab 02 builds this.)
- Rewrite Q3 in Polars and compare the results.
- Regenerate the data with `--days 365 --orders-per-day 5000` and compare query times.

## Clean up

```bash
rm -f lab.duckdb
```
