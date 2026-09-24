"""Reference solutions for Lab 03. Try exercises.py first.

Run one exercise:  python solutions.py 3
Run pipeline.py first; exercises 2-3 expect simulate_changes.py and a second pipeline run.
"""
from __future__ import annotations

import sys

from delta.tables import DeltaTable
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

from lake import LAKE_DIR, get_spark, path, read


def ex1_inspect_the_log(spark: SparkSession) -> None:
    """Q1: What is a Delta table on disk? List the files, then show the table history."""
    table = LAKE_DIR / "silver" / "orders"
    print("Data files:", len(list(table.glob("*.parquet"))))
    print("Commits:   ", sorted(p.name for p in (table / "_delta_log").glob("*.json")))
    (spark.sql(f"DESCRIBE HISTORY delta.`{path('silver', 'orders')}`")
          .select("version", "timestamp", "operation", "operationMetrics").show(truncate=60))


def ex2_merge_metrics(spark: SparkSession) -> None:
    """Q2: How many rows did the last MERGE insert and update in each silver table?"""
    for table in ["orders", "customers", "order_items", "events"]:
        last = (spark.sql(f"DESCRIBE HISTORY delta.`{path('silver', table)}` LIMIT 1")
                     .select("version", "operation",
                             F.col("operationMetrics.numTargetRowsInserted").alias("inserted"),
                             F.col("operationMetrics.numTargetRowsUpdated").alias("updated")))
        print(table); last.show()


def ex3_time_travel(spark: SparkSession) -> None:
    """Q3: Compare daily revenue now with version 0, and show only the days that changed."""
    now = read(spark, "gold", "daily_revenue").alias("now")
    before = read(spark, "gold", "daily_revenue", version=0).alias("before")
    (now.join(before, "order_date", "full_outer")
        .select("order_date",
                F.col("before.orders").alias("orders_before"), F.col("now.orders").alias("orders_now"),
                F.col("before.revenue_usd").alias("revenue_before"), F.col("now.revenue_usd").alias("revenue_now"))
        .where(~F.col("orders_before").eqNullSafe(F.col("orders_now"))
               | ~F.col("revenue_before").eqNullSafe(F.col("revenue_now")))
        .orderBy("order_date").show())


def ex4_customer_ranking(spark: SparkSession) -> None:
    """Q4: Top 3 customers by revenue in each country (DataFrame API, window function)."""
    orders = read(spark, "silver", "orders").where("status != 'cancelled'")
    lines = read(spark, "silver", "order_items")
    customers = read(spark, "silver", "customers").select("customer_id", "country")
    revenue = (lines.join(orders, "order_id")
                    .groupBy("customer_id")
                    .agg(F.round(F.sum(F.col("quantity") * F.col("unit_price")), 2).alias("revenue")))
    rank = Window.partitionBy("country").orderBy(F.col("revenue").desc())
    (revenue.join(customers, "customer_id")
            .withColumn("rank", F.rank().over(rank))
            .where("rank <= 3")
            .orderBy("country", "rank").show(30))


def ex5_schema_enforcement(spark: SparkSession) -> None:
    """Q5: Append a row with an extra column. Observe the error, then evolve the schema."""
    target = path("silver", "products")
    new = spark.createDataFrame(
        [(21, "SPO-0021", "Tennis Racket", "sports", 89.00, "red")],
        "product_id int, sku string, name string, category string, list_price double, colour string",
    ).withColumn("list_price", F.col("list_price").cast("decimal(10,2)"))
    try:
        new.write.format("delta").mode("append").save(target)
    except Exception as e:                                        # AnalysisException: schema mismatch
        print("Rejected:", str(e).splitlines()[0][:120])
    new.write.format("delta").mode("append").option("mergeSchema", "true").save(target)
    read(spark, "silver", "products").orderBy(F.col("product_id").desc()).show(3)
    # Undo, so the lab can be re-run: restore the version before the append
    table = DeltaTable.forPath(spark, target)
    before = table.history().where("operation = 'WRITE' AND operationParameters.mode = 'Append'") \
                  .agg(F.min("version")).first()[0] - 1
    table.restoreToVersion(before)
    print("Restored to version", before, "- columns:", read(spark, "silver", "products").columns)


def ex6_partition_pruning(spark: SparkSession) -> None:
    """Q6: Show that a filter on the partition column skips files, and compact small files."""
    events = read(spark, "silver", "events")
    print("Partitions:", len(list((LAKE_DIR / "silver" / "events").glob("event_date=*"))))
    events.where("event_date = '2024-03-15'").explain()        # look for PartitionFilters
    events.where("page = '/cart'").explain()                   # a DataFilter on every file
    table = DeltaTable.forPath(spark, path("silver", "events"))
    metrics = table.optimize().executeCompaction().select("metrics.numFilesAdded", "metrics.numFilesRemoved")
    metrics.show()


def ex7_late_events(spark: SparkSession) -> None:
    """Q7: Late data: what share of events arrived over an hour late, per day of the event?"""
    events = read(spark, "silver", "events")
    late = F.col("received_ts") > F.col("event_ts") + F.expr("INTERVAL 1 HOUR")
    (events.groupBy("event_date")
           .agg(F.count("*").alias("events"), F.sum(late.cast("int")).alias("late"))
           .withColumn("late_pct", F.round(100 * F.col("late") / F.col("events"), 2))
           .orderBy("event_date").show(5))
    # Late events for one day keep arriving for up to 30 hours, so a daily job needs a lookback window
    print("Max delay (hours):", events.select(F.max((F.col("received_ts").cast("long") - F.col("event_ts").cast("long")) / 3600)).first()[0])


EXERCISES = [ex1_inspect_the_log, ex2_merge_metrics, ex3_time_travel, ex4_customer_ranking,
             ex5_schema_enforcement, ex6_partition_pruning, ex7_late_events]

if __name__ == "__main__":
    selected = [int(a) for a in sys.argv[1:]] or range(1, len(EXERCISES) + 1)
    spark = get_spark("solutions")
    for n in selected:
        print(f"\n── Exercise {n}: {EXERCISES[n - 1].__doc__}")
        EXERCISES[n - 1](spark)
