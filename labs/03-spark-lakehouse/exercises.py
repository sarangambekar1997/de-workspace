"""Lab 03 exercises. Replace each TODO, then run:  python exercises.py 3

Every function runs as-is and prints a starting point. Reference answers: solutions.py.
Run pipeline.py first; exercises 2-3 expect simulate_changes.py and a second pipeline run.
"""
from __future__ import annotations

import sys

from delta.tables import DeltaTable  # noqa: F401  (needed for exercises 5-6)
from pyspark.sql import SparkSession, Window  # noqa: F401
from pyspark.sql import functions as F  # noqa: F401

from lake import LAKE_DIR, get_spark, path, read


def ex1_inspect_the_log(spark: SparkSession) -> None:
    """Q1: What is a Delta table on disk? List the files, then show the table history."""
    table = LAKE_DIR / "silver" / "orders"
    print(sorted(p.name for p in table.iterdir()))
    # TODO: count the Parquet files and list the commit files in _delta_log/
    # TODO: show DESCRIBE HISTORY for the table (version, timestamp, operation, operationMetrics)


def ex2_merge_metrics(spark: SparkSession) -> None:
    """Q2: How many rows did the last MERGE insert and update in each silver table?"""
    history = spark.sql(f"DESCRIBE HISTORY delta.`{path('silver', 'orders')}`")
    history.printSchema()
    # TODO: for orders, customers, order_items and events, show the latest version's
    #       numTargetRowsInserted and numTargetRowsUpdated from operationMetrics


def ex3_time_travel(spark: SparkSession) -> None:
    """Q3: Compare daily revenue now with version 0, and show only the days that changed."""
    now = read(spark, "gold", "daily_revenue")
    now.orderBy(F.col("order_date").desc()).show(3)
    # TODO: read version 0 of the same table, join on order_date (a new day exists only in one version),
    #       and keep rows where orders or revenue differ. Hint: Column.eqNullSafe


def ex4_customer_ranking(spark: SparkSession) -> None:
    """Q4: Top 3 customers by revenue in each country (DataFrame API, window function)."""
    customers = read(spark, "silver", "customers")
    customers.groupBy("country").count().orderBy("country").show()
    # TODO: revenue per customer from silver orders (excluding cancelled) and order_items,
    #       then rank within each country with Window.partitionBy(...).orderBy(...) and F.rank()


def ex5_schema_enforcement(spark: SparkSession) -> None:
    """Q5: Append a row with an extra column. Observe the error, then evolve the schema."""
    read(spark, "silver", "products").printSchema()
    # TODO: append a product with an extra `colour` column and catch the error
    # TODO: append again with .option("mergeSchema", "true"); what happens to existing rows?
    # TODO: undo it with DeltaTable.forPath(...).restoreToVersion(...)


def ex6_partition_pruning(spark: SparkSession) -> None:
    """Q6: Show that a filter on the partition column skips files, and compact small files."""
    print(sorted(p.name for p in (LAKE_DIR / "silver" / "events").glob("event_date=*"))[:5])
    # TODO: compare .explain() for a filter on event_date and a filter on page.
    #       Which one shows PartitionFilters, and which DataFilters?
    # TODO: compact files with DeltaTable.forPath(...).optimize().executeCompaction()


def ex7_late_events(spark: SparkSession) -> None:
    """Q7: Late data: what share of events arrived over an hour late, per day of the event?"""
    read(spark, "silver", "events").select("event_ts", "received_ts").show(3)
    # TODO: per event_date, count events and late events (received over 1 hour after event_ts)
    # TODO: find the maximum delay in hours. What does it mean for a daily job?


EXERCISES = [ex1_inspect_the_log, ex2_merge_metrics, ex3_time_travel, ex4_customer_ranking,
             ex5_schema_enforcement, ex6_partition_pruning, ex7_late_events]

if __name__ == "__main__":
    selected = [int(a) for a in sys.argv[1:]] or range(1, len(EXERCISES) + 1)
    spark = get_spark("exercises")
    for n in selected:
        print(f"\n── Exercise {n}: {EXERCISES[n - 1].__doc__}")
        EXERCISES[n - 1](spark)
