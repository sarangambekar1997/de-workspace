# Lab 02 — dbt Transformations

Turn the raw e-commerce files into tested, documented models with dbt: staging, intermediate and mart layers, data tests, unit tests, an incremental model, and an SCD Type 2 snapshot.

| | |
|-|-|
| **Time** | 90–120 minutes |
| **Runs on** | Python + dbt + DuckDB (no Docker, no server, no cloud account) |
| **Guides** | [dbt](../../docs/02-processing/dbt-reference.md) · [Data Modeling](../../docs/01-storage/data-modeling.md) · [Data Quality](../../docs/05-quality-governance/data-quality.md) |
| **Before this** | [Lab 01](../01-sql-analytics/README.md) introduces the dataset and its data quality problems |

## Setup

```bash
cd labs/02-dbt-transformations
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python ../data/generate.py          # writes ../data/output/*.csv and events.jsonl
dbt debug                           # checks the connection; profiles.yml in this folder is used
dbt build                           # seeds, models, snapshot, and tests — expect PASS=35 WARN=1
```

Run every `dbt` command from this folder. The project reads the generated files in place and writes to `shop.duckdb`.

To query the results, use the DuckDB CLI (`duckdb shop.duckdb`) or Python:

```bash
python -c "import duckdb; duckdb.connect('shop.duckdb').sql('select * from marts.fct_daily_revenue order by 1 desc limit 5').show()"
```

## Project

```text
models/
├── staging/          # one view per source: rename, cast, deduplicate — no business logic
│   ├── _sources.yml  #   the raw files, declared as dbt sources
│   └── _staging.yml  #   tests, plus a unit test for the deduplication
├── intermediate/     # int_order_lines__valid: joins lines to orders, products and rates; flags bad lines
└── marts/            # tables for analysts: dim_customer, dim_product, fct_orders, fct_daily_revenue
seeds/                # currency_rates.csv — a small reference table kept in Git
snapshots/            # snap_customers — SCD Type 2 history of customer country
tests/                # singular (custom SQL) tests
macros/               # generate_schema_name: schemas are named staging, marts, ... without a prefix
```

| Model | Materialization | Shows |
|-------|-----------------|-------|
| `stg_raw__orders` | view | Deduplication with `QUALIFY`, a unit test, a `warn`-severity test for a known source issue |
| `int_order_lines__valid` | view | Flagging invalid rows with a status instead of silently dropping them |
| `fct_orders` | table | Order grain, revenue from valid lines only |
| `fct_daily_revenue` | incremental | `delete+insert` with a 3-day lookback for late-changing data |
| `snap_customers` | snapshot | SCD Type 2 using the `timestamp` strategy |

## Exercises

Reference solutions are in [`solutions/`](solutions/), using the same folder layout as the project. To check one, copy it into place and run `dbt build`.

| # | Task | Concepts |
|---|------|----------|
| 1 | Build and explore | Lineage, test severity |
| 2 | Customer lifetime value mart | Refs, grain, generic tests |
| 3 | Revenue reconciliation test | Singular tests |
| 4 | Unit test the line classification | Unit tests, fixtures |
| 5 | Process a day of source changes | Incremental models, snapshots |
| 6 | Revenue by country at order time | Point-in-time joins on SCD Type 2 |

### 1. Build and explore

1. Run `dbt build` and read the output. One test ends in `WARN`, not `ERROR`. Find it in [`_staging.yml`](models/staging/_staging.yml): why is it configured this way, and when would `error` be the better choice?
2. List everything upstream of the daily revenue fact: `dbt ls --select +fct_daily_revenue`.
3. Open `target/compiled/shop/models/marts/fct_daily_revenue.sql` and compare it with the model source. What did `{{ ref(...) }}` compile to?
4. Optional: `dbt docs generate && dbt docs serve` opens the documentation site with a lineage graph.

### 2. Customer lifetime value mart

Create `models/marts/fct_customer_ltv.sql` with **one row per customer**, including customers who never ordered: country, first and last order date, number of orders, lifetime value in USD, and a repeat-customer flag. Exclude cancelled orders.

Add a YAML file that tests `customer_id` is unique and not null, then run `dbt build --select fct_customer_ltv`.

Hint: start from `dim_customer` and `LEFT JOIN` the orders, so customers with no orders keep a row. About 57% of customers who ordered are repeat customers.

Solution: [`fct_customer_ltv.sql`](solutions/models/marts/fct_customer_ltv.sql), [`_customer_ltv.yml`](solutions/models/marts/_customer_ltv.yml)

### 3. Revenue reconciliation test

`fct_daily_revenue` and `fct_orders` compute revenue separately. Write a singular test in `tests/` that fails if their totals differ by more than 1 USD.

A singular test is a `SELECT` that returns the failing rows, so the test passes when the query returns nothing.

Solution: [`assert_daily_revenue_reconciles.sql`](solutions/tests/assert_daily_revenue_reconciles.sql)

### 4. Unit test the line classification

`int_order_lines__valid` assigns each line a `line_status`: `valid`, `unknown_product`, `non_positive_quantity` or `cancelled_order`. Write a unit test in `models/intermediate/_intermediate.yml` with one input row for each case, and check both the status and `line_amount_usd`.

Unit tests replace every `ref()` with the rows you give, so provide inputs for all four upstream models. Look at `test_orders_keep_latest_version` in [`_staging.yml`](models/staging/_staging.yml) for the format. Every expected row must list the same columns.

Solution: [`_intermediate.yml`](solutions/models/intermediate/_intermediate.yml)

### 5. Process a day of source changes

Real sources change after they are loaded. This step applies one day of changes, then shows how the incremental model and the snapshot deal with them.

```bash
# Record the state before the changes
python -c "import duckdb; duckdb.connect('shop.duckdb').sql('select * from marts.fct_daily_revenue order by 1 desc limit 4').show()"

python ../data/simulate_changes.py     # new day of orders, one late cancellation, three customers move
dbt build
```

1. `fct_daily_revenue` now has a row for 2024-03-31. The value for 2024-03-29 also changed, because an order from that day was cancelled. Which part of the model made it reprocess that day, and what would happen to the late cancellation without it?
2. Open `target/compiled/shop/models/marts/fct_daily_revenue.sql` to see the date filter that `is_incremental()` added, and `target/run/shop/models/marts/fct_daily_revenue.sql` to see how dbt applied the result. Which dates were deleted and re-inserted?
3. What does `dbt build --full-refresh --select fct_daily_revenue` do, and when would you need it?
4. Query the snapshot for the customers who moved:

   ```sql
   select customer_id, country, dbt_valid_from, dbt_valid_to
   from snapshots.snap_customers
   where customer_id in (7, 42, 99)
   order by customer_id, dbt_valid_from;
   ```

   Each customer now has two rows. The current version is the one with `dbt_valid_to` null.

To start over, run `python ../data/generate.py` and delete `shop.duckdb`.

### 6. Revenue by country at order time

In Lab 01, revenue by country used each customer's **current** country. Create `models/marts/fct_revenue_by_country.sql`, which reports revenue by the country the customer lived in **when the order was placed**, using `snap_customers`.

Hints:
- Join an order to the customer version where `order_ts >= dbt_valid_from` and `order_ts < dbt_valid_to`. Treat a null `dbt_valid_to` as far in the future.
- The snapshot only starts recording when it first runs, so the earliest version of each customer has a `dbt_valid_from` later than some of their orders. Decide how to cover that gap.
- Orders with no customer should still count, under `unknown`.
- Check your result: the revenue across all countries should equal the total revenue in `fct_orders`, excluding cancelled orders.

Solution: [`fct_revenue_by_country.sql`](solutions/models/marts/fct_revenue_by_country.sql)

## Going further

- Add `accepted_values` tests for `currency` and `event_type`, and a `relationships` test from order items to products. Which of them fail on this data, and should they fail the build or only warn?
- Add a `dim_date` model and join the daily fact to it.
- Replace `delete+insert` with the `merge` strategy. What changes in the compiled SQL?
- Point `profiles.yml` at a cloud warehouse such as Snowflake, BigQuery or Databricks. The staging models use DuckDB syntax (`::` casts, `read_csv`), so note what needs to change.

## Clean up

```bash
dbt clean            # removes target/
rm -f shop.duckdb
```
