# Data Quality for Data Engineers
> Frameworks, patterns, and tools for building reliable data pipelines.

**Prerequisites:** [SQL](../00-foundations/sql-reference.md)

**Related:** [dbt](../02-processing/dbt-reference.md) · [Airflow](../03-orchestration/airflow-reference.md) · [Evals](../07-ai/eval-and-evals.md) · [Glossary](../99-reference/glossary.md)

---

## Table of Contents

**Basics**
- [Why Data Quality Matters](#why-data-quality-matters)
- [The Five Dimensions](#the-five-dimensions)
- [SQL-Based Checks](#sql-based-checks)
- [Python-Based Validation](#python-based-validation)

**Intermediate**
- [dbt Tests](#dbt-tests)
- [Great Expectations](#great-expectations)
- [Anomaly Detection Patterns](#anomaly-detection-patterns)
- [Data Contracts](#data-contracts)

**Advanced**
- [DQ in Streaming Pipelines](#dq-in-streaming-pipelines)
- [Observability & Alerting](#observability--alerting)
- [SLA Monitoring](#sla-monitoring)
- [Building a DQ Framework](#building-a-dq-framework)

---

## Why Data Quality Matters

Bad data is worse than no data — it leads to wrong decisions made with confidence.

```
Common failure modes:
  Upstream schema change  → pipeline silently loads wrong types
  NULL in required column → downstream joins produce wrong counts
  Duplicate events        → revenue overstated by 12%
  Stale data              → dashboard shows yesterday's numbers as today's
  Row count drop (50%)    → partial load treated as complete
```

**The cost of catching DQ issues late:**

```
At ingestion:  fix the source, re-run — 30 minutes
At transform:  re-run dbt models — 2 hours
At serving:    correct BI reports, notify stakeholders — 1 day
After decision: retract analysis, rebuild trust — weeks
```

---

## The Five Dimensions

| Dimension | Question | Example failure |
|-----------|----------|----------------|
| **Completeness** | Is all expected data present? | Orders table missing 3 days of data |
| **Accuracy** | Does it reflect reality? | Negative order amounts after a sign error |
| **Consistency** | Does it agree across systems? | Revenue in warehouse ≠ revenue in source DB |
| **Timeliness** | Is it fresh enough? | Daily report using yesterday's data at 9am |
| **Uniqueness** | Are there duplicates? | Customer counted twice after a dedup bug |

---

## SQL-Based Checks

The simplest DQ checks are SQL queries that return rows on failure. Zero rows = pass.

```sql
-- ── Completeness ─────────────────────────────────
-- Required columns have no NULLs
SELECT COUNT(*) AS null_count
FROM orders
WHERE order_id IS NULL OR amount IS NULL;

-- Expected row count
SELECT COUNT(*) AS row_count FROM orders WHERE order_date = '2024-03-15';
-- Alert if row_count < 1000 (or below historical average)

-- All expected sources present
SELECT DISTINCT source
FROM orders
WHERE order_date = CURRENT_DATE - 1
-- Alert if any expected source is missing from the result

-- ── Accuracy ─────────────────────────────────────
-- No negative amounts
SELECT order_id, amount
FROM orders
WHERE amount < 0;

-- Valid status values
SELECT DISTINCT status FROM orders
WHERE status NOT IN ('placed', 'shipped', 'delivered', 'cancelled', 'returned');

-- Age within realistic bounds
SELECT customer_id, age
FROM customers
WHERE age < 0 OR age > 130;

-- Prices within expected range
SELECT product_id, price
FROM products
WHERE price <= 0 OR price > 100000;

-- ── Consistency ───────────────────────────────────
-- Row count matches source
SELECT
    (SELECT COUNT(*) FROM warehouse.orders WHERE order_date = '2024-03-15') AS wh_count,
    (SELECT COUNT(*) FROM source_db.orders WHERE DATE(created_at) = '2024-03-15') AS src_count;
-- Alert if ABS(wh_count - src_count) > 0

-- Revenue reconciliation
SELECT
    ABS(wh.revenue - src.revenue) AS discrepancy,
    wh.revenue AS warehouse_revenue,
    src.revenue AS source_revenue
FROM (
    SELECT SUM(amount) AS revenue FROM warehouse.orders WHERE order_date = '2024-03-15'
) wh,
(
    SELECT SUM(amount) AS revenue FROM source_db.orders WHERE DATE(created_at) = '2024-03-15'
) src
WHERE ABS(wh.revenue - src.revenue) > 0.01;  -- allow 1 cent rounding

-- ── Uniqueness ────────────────────────────────────
-- No duplicate primary keys
SELECT order_id, COUNT(*) AS n
FROM orders
GROUP BY order_id
HAVING COUNT(*) > 1;

-- No duplicate events (by business key + timestamp window)
SELECT user_id, event_type, DATE_TRUNC('minute', event_time) AS minute, COUNT(*)
FROM events
GROUP BY 1, 2, 3
HAVING COUNT(*) > 3;  -- more than 3 identical events in a minute = suspicious

-- ── Timeliness ────────────────────────────────────
-- Data is fresh enough
SELECT MAX(updated_at) AS latest_record,
       DATEDIFF('hour', MAX(updated_at), CURRENT_TIMESTAMP()) AS hours_old
FROM orders;
-- Alert if hours_old > 2

-- Referential integrity
SELECT o.order_id
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.id
WHERE c.id IS NULL;  -- orders with no matching customer
```

---

## Python-Based Validation

```python
import pandas as pd
from dataclasses import dataclass
from typing import Callable

@dataclass
class Check:
    name: str
    fn: Callable[[pd.DataFrame], bool]
    severity: str = "error"   # "error" | "warning"

def run_checks(df: pd.DataFrame, checks: list[Check]) -> dict:
    results = []
    for check in checks:
        passed = check.fn(df)
        results.append({
            "check": check.name,
            "passed": passed,
            "severity": check.severity,
        })
        if not passed and check.severity == "error":
            raise ValueError(f"DQ check FAILED: {check.name}")
    return results

# Define checks
checks = [
    Check("no_null_order_id",
          lambda df: df["order_id"].notnull().all()),

    Check("no_negative_amount",
          lambda df: (df["amount"] >= 0).all()),

    Check("valid_status",
          lambda df: df["status"].isin(["placed","shipped","delivered","cancelled","returned"]).all()),

    Check("no_duplicate_order_ids",
          lambda df: df["order_id"].nunique() == len(df)),

    Check("row_count_above_minimum",
          lambda df: len(df) >= 1000,
          severity="warning"),

    Check("amount_in_range",
          lambda df: df["amount"].between(0, 100_000).all()),
]

df = pd.read_parquet("s3://bucket/orders/2024-03-15/")
results = run_checks(df, checks)
print(f"Passed: {sum(r['passed'] for r in results)}/{len(results)}")
```

---

## dbt Tests

See also [dbt Reference](../02-processing/dbt-reference.md) for full dbt test coverage.

```yaml
# Four built-in generic tests
models:
  - name: fct_orders
    columns:
      - name: order_id
        data_tests:
          - unique
          - not_null
      - name: status
        data_tests:
          - accepted_values:
              values: ['placed', 'shipped', 'delivered', 'cancelled']
      - name: customer_id
        data_tests:
          - relationships:
              to: ref('dim_customer')
              field: customer_id
```

### Custom singular test

```sql
-- tests/assert_revenue_matches_source.sql
-- Fails if revenue discrepancy > $1
WITH warehouse AS (
    SELECT SUM(amount) AS revenue
    FROM {{ ref('fct_orders') }}
    WHERE order_date = CURRENT_DATE - 1
),
source AS (
    SELECT SUM(amount) AS revenue
    FROM {{ source('raw', 'orders') }}
    WHERE DATE(created_at) = CURRENT_DATE - 1
)
SELECT
    warehouse.revenue AS wh_revenue,
    source.revenue    AS src_revenue,
    ABS(warehouse.revenue - source.revenue) AS discrepancy
FROM warehouse, source
WHERE ABS(warehouse.revenue - source.revenue) > 1.0
```

### dbt-expectations (extended tests)

```yaml
columns:
  - name: amount
    data_tests:
      - dbt_expectations.expect_column_values_to_be_between:
          min_value: 0
          max_value: 100000
      - dbt_expectations.expect_column_mean_to_be_between:
          min_value: 50
          max_value: 500

  - name: created_at
    data_tests:
      - dbt_expectations.expect_column_values_to_be_of_type:
          column_type: timestamp_ntz

models:
  - name: fct_orders
    data_tests:
      - dbt_expectations.expect_table_row_count_to_be_between:
          min_value: 1000
      - dbt_expectations.expect_table_columns_to_match_ordered_list:
          column_list: [order_id, customer_id, amount, status, created_at]
```

---

## Great Expectations

Great Expectations is a Python library for defining, running, and documenting data quality checks.

### Core concepts

| Concept | Definition |
|---------|-----------|
| **Expectation** | A verifiable assertion about data (e.g. "order_id is never null") |
| **Expectation Suite** | A collection of expectations for one dataset |
| **Checkpoint** | Connects a data source + expectation suite + action (alert, save results) |
| **Data Docs** | Auto-generated HTML documentation of all suites and results |
| **Validation Result** | The output of running an expectation suite — pass/fail + stats |

### Setup and basic usage

```python
import great_expectations as gx
import pandas as pd

# Initialize context (stores config, suites, results)
context = gx.get_context()

# Create a data source
datasource = context.sources.add_pandas("orders_source")

# Create a data asset
asset = datasource.add_csv_asset(
    name="orders",
    filepath_or_buffer="s3://my-bucket/orders/2024-03-15/orders.csv"
)

# Build expectation suite
suite = context.add_expectation_suite("orders_suite")

# Define expectations
batch = context.get_validator(
    batch_request=asset.build_batch_request(),
    expectation_suite_name="orders_suite"
)

batch.expect_column_to_exist("order_id")
batch.expect_column_values_to_not_be_null("order_id")
batch.expect_column_values_to_be_unique("order_id")
batch.expect_column_values_to_not_be_null("amount")
batch.expect_column_values_to_be_between("amount", min_value=0, max_value=100000)
batch.expect_column_values_to_be_in_set("status",
    value_set=["placed", "shipped", "delivered", "cancelled"])
batch.expect_table_row_count_to_be_between(min_value=1000, max_value=10000000)
batch.expect_column_pair_values_to_be_greater_than(
    "updated_at", "created_at"
)

# Save expectations
batch.save_expectation_suite()

# Validate
results = batch.validate()
print(results["success"])    # True / False
print(results["statistics"]) # counts of passed/failed

# Run as checkpoint (with actions — save results, send alert)
checkpoint = context.add_checkpoint(
    name="orders_checkpoint",
    validations=[{"batch_request": asset.build_batch_request(),
                  "expectation_suite_name": "orders_suite"}],
    action_list=[
        {"name": "store_validation_result",
         "action": {"class_name": "StoreValidationResultAction"}},
        {"name": "update_data_docs",
         "action": {"class_name": "UpdateDataDocsAction"}},
    ]
)
result = checkpoint.run()
```

### Common expectations

```python
# Column existence
expect_column_to_exist("order_id")

# Null checks
expect_column_values_to_not_be_null("order_id")
expect_column_proportion_of_unique_values_to_be_between("status", min_value=0.0, max_value=0.01)

# Value set
expect_column_values_to_be_in_set("status", ["placed","shipped","delivered"])
expect_column_values_to_not_be_in_set("country_code", ["XX", "ZZ"])

# Range
expect_column_values_to_be_between("amount", min_value=0, max_value=100000)
expect_column_mean_to_be_between("amount", min_value=10, max_value=1000)
expect_column_stdev_to_be_between("amount", min_value=0, max_value=500)

# Type
expect_column_values_to_be_of_type("order_id", "str")
expect_column_values_to_match_regex("email", r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# Table-level
expect_table_row_count_to_be_between(min_value=1000)
expect_table_columns_to_match_set({"order_id", "customer_id", "amount", "status"})

# Referential
expect_column_values_to_be_in_type_list("created_at", ["datetime64[ns]", "Timestamp"])

# Multi-column
expect_column_pair_values_a_to_be_greater_than_b("updated_at", "created_at")
```

---

## Anomaly Detection Patterns

Statistical checks that catch unusual-but-valid-looking data.

```sql
-- Row count anomaly — alert if today's count is below 3-sigma of the past 30 days
WITH daily_counts AS (
    SELECT order_date, COUNT(*) AS n
    FROM orders
    WHERE order_date >= CURRENT_DATE - 31
    GROUP BY order_date
),
stats AS (
    SELECT
        AVG(n)    AS mean_n,
        STDDEV(n) AS std_n
    FROM daily_counts
    WHERE order_date < CURRENT_DATE  -- exclude today
)
SELECT d.order_date, d.n,
    s.mean_n,
    s.mean_n - 3 * s.std_n AS lower_bound,
    CASE WHEN d.n < s.mean_n - 3 * s.std_n THEN 'ALERT' ELSE 'OK' END AS status
FROM daily_counts d, stats s
WHERE d.order_date = CURRENT_DATE;

-- Revenue anomaly — percentage change from same weekday 4 weeks ago
WITH today AS (
    SELECT SUM(amount) AS revenue FROM orders WHERE order_date = CURRENT_DATE
),
baseline AS (
    SELECT AVG(SUM(amount)) AS avg_revenue
    FROM orders
    WHERE order_date IN (
        CURRENT_DATE - 7,
        CURRENT_DATE - 14,
        CURRENT_DATE - 21,
        CURRENT_DATE - 28
    )
    GROUP BY DAYOFWEEK(order_date)
    HAVING DAYOFWEEK(order_date) = DAYOFWEEK(CURRENT_DATE)
)
SELECT
    today.revenue,
    baseline.avg_revenue,
    (today.revenue - baseline.avg_revenue) / baseline.avg_revenue * 100 AS pct_change
FROM today, baseline;
```

```python
# Python: Z-score based anomaly detection
import pandas as pd
import numpy as np

def detect_anomalies(df: pd.DataFrame, col: str, window_days: int = 30, z_threshold: float = 3.0) -> pd.DataFrame:
    """Flag rows where the value is beyond z_threshold standard deviations from the rolling mean."""
    rolling = df[col].rolling(window=window_days, min_periods=7)
    df["rolling_mean"] = rolling.mean()
    df["rolling_std"]  = rolling.std()
    df["z_score"]      = (df[col] - df["rolling_mean"]) / df["rolling_std"]
    df["is_anomaly"]   = df["z_score"].abs() > z_threshold
    return df
```

---

## Data Contracts

A data contract is a formal agreement between a data producer and consumer defining the schema, semantics, SLAs, and quality guarantees of a dataset.

```yaml
# data_contract.yaml — example
name: orders
version: "1.2.0"
description: "Transactional orders from the e-commerce platform"
owner: "data-engineering@company.com"
updated_at: "2024-03-15"

schema:
  fields:
    - name: order_id
      type: string
      nullable: false
      unique: true
      description: "UUID v4 order identifier"

    - name: customer_id
      type: integer
      nullable: false
      description: "FK to dim_customer"

    - name: amount
      type: decimal(12,2)
      nullable: false
      constraints:
        min: 0
        max: 100000

    - name: status
      type: string
      nullable: false
      constraints:
        enum: [placed, shipped, delivered, cancelled, returned]

    - name: created_at
      type: timestamp
      nullable: false

quality:
  row_count_min_daily: 10000
  freshness_sla_hours: 2
  completeness_min_pct: 99.9

sla:
  availability: "99.9%"
  freshness: "data available by 06:00 UTC"
  support_contact: "data-team@example.com"
```

---

## DQ in Streaming Pipelines

```python
# PySpark Structured Streaming with inline DQ checks
from pyspark.sql import functions as F

def validate_streaming_batch(df, epoch_id):
    """Called for each micro-batch — apply DQ checks before writing."""

    # Null check
    null_count = df.filter(F.col("order_id").isNull()).count()
    if null_count > 0:
        raise ValueError(f"Batch {epoch_id}: {null_count} null order_ids")

    # Negative amount check
    bad_amounts = df.filter(F.col("amount") < 0)
    if bad_amounts.count() > 0:
        # Route bad records to quarantine, not main table
        bad_amounts.write.mode("append").parquet("s3://bucket/quarantine/orders/")
        df = df.filter(F.col("amount") >= 0)

    # Write clean records
    df.write.format("delta").mode("append").save("s3://bucket/silver/orders/")

stream = (
    spark.readStream.format("kafka")
        .option("subscribe", "order-events")
        .load()
        .select(F.from_json(F.col("value").cast("string"), order_schema).alias("d"))
        .select("d.*")
)

stream.writeStream \
    .foreachBatch(validate_streaming_batch) \
    .option("checkpointLocation", "s3://checkpoints/orders/") \
    .start()
```

### DLT expectations (Databricks)

```python
import dlt
from pyspark.sql import functions as F

@dlt.table
@dlt.expect("valid_amount",    "amount >= 0")
@dlt.expect_or_drop("has_order_id",    "order_id IS NOT NULL")
@dlt.expect_or_fail("valid_status",    "status IN ('placed','shipped','delivered','cancelled')")
def orders_silver():
    return dlt.read_stream("orders_bronze") \
               .withColumn("amount", F.col("amount").cast("double"))
```

---

## Observability & Alerting

### Log DQ results to a table

```python
from datetime import datetime

def log_dq_result(spark, pipeline_name, table_name, check_name,
                  passed, row_count, details=None):
    record = [{
        "pipeline":    pipeline_name,
        "table":       table_name,
        "check":       check_name,
        "passed":      passed,
        "row_count":   row_count,
        "details":     details,
        "checked_at":  datetime.utcnow().isoformat(),
    }]
    spark.createDataFrame(record) \
         .write.format("delta").mode("append") \
         .saveAsTable("ops.dq_results")
```

### Alert on failure

```python
import requests

def slack_alert(check_name: str, table: str, details: str, webhook_url: str):
    msg = {
        "text": f":red_circle: *DQ Check Failed*\n"
                f"*Check:* `{check_name}`\n"
                f"*Table:* `{table}`\n"
                f"*Details:* {details}"
    }
    requests.post(webhook_url, json=msg)

def run_check_with_alert(df, check_fn, check_name, table, webhook_url):
    passed = check_fn(df)
    if not passed:
        slack_alert(check_name, table,
                    f"Check failed for {len(df)} rows",
                    webhook_url)
        raise ValueError(f"DQ check failed: {check_name}")
```

---

## SLA Monitoring

```sql
-- Track pipeline freshness SLA
-- Alert if MAX(updated_at) is older than the SLA threshold

WITH slas AS (
    SELECT 'orders'    AS table_name, 2  AS sla_hours UNION ALL
    SELECT 'customers' AS table_name, 24 AS sla_hours UNION ALL
    SELECT 'events'    AS table_name, 1  AS sla_hours
),
freshness AS (
    SELECT 'orders'    AS table_name, MAX(updated_at) AS latest_ts FROM orders UNION ALL
    SELECT 'customers' AS table_name, MAX(updated_at)              FROM customers UNION ALL
    SELECT 'events'    AS table_name, MAX(event_time)              FROM events
)
SELECT
    s.table_name,
    f.latest_ts,
    s.sla_hours,
    DATEDIFF('hour', f.latest_ts, CURRENT_TIMESTAMP()) AS hours_stale,
    CASE
        WHEN DATEDIFF('hour', f.latest_ts, CURRENT_TIMESTAMP()) > s.sla_hours
        THEN 'SLA BREACHED'
        ELSE 'OK'
    END AS status
FROM slas s
JOIN freshness f USING (table_name)
ORDER BY hours_stale DESC;
```

---

## Building a DQ Framework

A minimal production DQ framework has four components:

```
1. Check definitions  — what to validate (SQL or Python)
2. Check runner       — execute checks, capture results
3. Result store       — persist results for trending and alerting
4. Alerting           — notify on failures, SLA breaches, anomalies
```

```python
# Minimal framework skeleton
from dataclasses import dataclass
from typing import Callable
from datetime import datetime
import pandas as pd

@dataclass
class DQCheck:
    name:     str
    fn:       Callable[[pd.DataFrame], bool]
    severity: str = "error"    # "error" blocks pipeline; "warning" logs only

class DQRunner:
    def __init__(self, pipeline: str, table: str, alert_fn=None):
        self.pipeline  = pipeline
        self.table     = table
        self.alert_fn  = alert_fn
        self.results   = []

    def run(self, df: pd.DataFrame, checks: list[DQCheck]) -> bool:
        all_passed = True
        for check in checks:
            try:
                passed = check.fn(df)
            except Exception as e:
                passed = False

            self.results.append({
                "pipeline":   self.pipeline,
                "table":      self.table,
                "check":      check.name,
                "passed":     passed,
                "severity":   check.severity,
                "checked_at": datetime.utcnow().isoformat(),
            })

            if not passed:
                if check.severity == "error":
                    all_passed = False
                if self.alert_fn:
                    self.alert_fn(check.name, self.table, check.severity)

        return all_passed

    def raise_on_failure(self):
        failed = [r for r in self.results if not r["passed"] and r["severity"] == "error"]
        if failed:
            names = ", ".join(r["check"] for r in failed)
            raise ValueError(f"DQ checks failed: {names}")
```

---

**Previous:** [dbt](../02-processing/dbt-reference.md) · **Next:** [Airflow](../03-orchestration/airflow-reference.md) · **Back to:** [Index](../README.md)
