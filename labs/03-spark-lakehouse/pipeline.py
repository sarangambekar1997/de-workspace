"""Medallion pipeline: raw files -> bronze -> silver -> gold, stored as Delta tables.

    bronze  raw rows as strings, plus ingestion metadata; one batch appended per run
    silver  typed, deduplicated, validated; kept current with MERGE (upserts)
    gold    business aggregates, rebuilt from silver on each run

Usage:
    python pipeline.py            # run all layers; safe to re-run
"""
from __future__ import annotations

from datetime import datetime, timezone

from delta.tables import DeltaTable
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from lake import RAW_DIR, get_spark, path, read

CSV_SOURCES = ["customers", "products", "orders", "order_items"]


# ── Bronze ────────────────────────────────────────────────────────────────────
def load_bronze(spark: SparkSession, batch_id: str) -> None:
    """Append every raw file as one batch. Columns stay strings: bronze never rejects data."""
    for name in CSV_SOURCES:
        df = spark.read.option("header", True).csv(str(RAW_DIR / f"{name}.csv"))
        _append_bronze(df, name, batch_id)
    # JSON Lines: read as text so malformed lines are kept, parsed in silver
    events = spark.read.text(str(RAW_DIR / "events.jsonl")).withColumnRenamed("value", "raw_json")
    _append_bronze(events, "events", batch_id)


def _append_bronze(df: DataFrame, name: str, batch_id: str) -> None:
    (df.withColumn("_batch_id", F.lit(batch_id))
       .withColumn("_source_file", F.input_file_name())
       .withColumn("_ingested_at", F.current_timestamp())
       .write.format("delta").mode("append").save(path("bronze", name)))


def latest_batch(spark: SparkSession, name: str) -> DataFrame:
    df = read(spark, "bronze", name)
    last = df.agg(F.max("_batch_id")).first()[0]
    return df.where(F.col("_batch_id") == last)


# ── Silver ────────────────────────────────────────────────────────────────────
def upsert(spark: SparkSession, df: DataFrame, table: str, keys: list[str],
           partition_by: list[str] | None = None) -> None:
    """Create the table on first run; afterwards MERGE: update changed rows, insert new ones."""
    target = path("silver", table)
    if not DeltaTable.isDeltaTable(spark, target):
        df.write.format("delta").partitionBy(*(partition_by or [])).save(target)
        return
    condition = " AND ".join(f"t.{k} = s.{k}" for k in keys)
    merge = DeltaTable.forPath(spark, target).alias("t").merge(df.alias("s"), condition)
    if "updated_at" in df.columns:
        # Only overwrite with a newer version: replays and out-of-order batches are harmless
        merge = merge.whenMatchedUpdateAll(condition="s.updated_at > t.updated_at")
    merge.whenNotMatchedInsertAll().execute()


def build_silver(spark: SparkSession) -> None:
    latest = Window.partitionBy("order_id").orderBy(F.col("updated_at").desc())
    orders = (
        latest_batch(spark, "orders")
        .select(
            F.col("order_id").cast("bigint"),
            F.col("customer_id").cast("int"),
            F.to_timestamp("order_ts").alias("order_ts"),
            F.lower("status").alias("status"),
            "currency",
            F.to_timestamp("updated_at").alias("updated_at"),
        )
        .withColumn("_rn", F.row_number().over(latest))
        .where("_rn = 1").drop("_rn")
    )
    upsert(spark, orders, "orders", ["order_id"])

    customers = latest_batch(spark, "customers").select(
        F.col("customer_id").cast("int"), "email", "first_name", "country",
        F.to_date("signup_date").alias("signup_date"),
        F.to_timestamp("updated_at").alias("updated_at"),
    )
    upsert(spark, customers, "customers", ["customer_id"])

    products = latest_batch(spark, "products").select(
        F.col("product_id").cast("int"), "sku", "name", "category",
        F.col("unit_price").cast("decimal(10,2)").alias("list_price"),
    )
    upsert(spark, products, "products", ["product_id"])

    # Order lines: valid rows go to silver, invalid ones to a quarantine table with a reason
    lines = latest_batch(spark, "order_items").select(
        F.col("order_id").cast("bigint"), F.col("line_no").cast("int"),
        F.col("product_id").cast("int"), F.col("quantity").cast("int"),
        F.col("unit_price").cast("decimal(10,2)"),
    )
    known = read(spark, "silver", "products").select("product_id", F.lit(True).alias("_known"))
    checked = lines.join(F.broadcast(known), "product_id", "left").withColumn(
        "reject_reason",
        F.when(F.col("_known").isNull(), "unknown_product")
         .when(F.col("quantity") <= 0, "non_positive_quantity"),
    ).drop("_known")
    upsert(spark, checked.where("reject_reason IS NULL").drop("reject_reason"),
           "order_items", ["order_id", "line_no"])
    upsert(spark, checked.where("reject_reason IS NOT NULL"),
           "order_items_quarantine", ["order_id", "line_no"])

    # Events: parse JSON, drop duplicate deliveries, partition by event date
    schema = "event_id BIGINT, customer_id INT, event_type STRING, page STRING, event_ts STRING, received_ts STRING"
    first = Window.partitionBy("event_id").orderBy("received_ts")
    events = (
        latest_batch(spark, "events")
        .select(F.from_json("raw_json", schema).alias("e")).select("e.*")
        .withColumn("event_ts", F.to_timestamp("event_ts"))
        .withColumn("received_ts", F.to_timestamp("received_ts"))
        .withColumn("event_date", F.to_date("event_ts"))
        .withColumn("_rn", F.row_number().over(first)).where("_rn = 1").drop("_rn")
    )
    upsert(spark, events, "events", ["event_id"], partition_by=["event_date"])


# ── Gold ──────────────────────────────────────────────────────────────────────
def build_gold(spark: SparkSession) -> None:
    orders = read(spark, "silver", "orders").where("status != 'cancelled'")
    lines = read(spark, "silver", "order_items")
    products = read(spark, "silver", "products").select("product_id", "category")
    rates = spark.createDataFrame([("USD", 1.00), ("EUR", 1.09), ("GBP", 1.27)], "currency string, rate_to_usd double")

    sales = (
        lines.join(orders, "order_id").join(products, "product_id").join(F.broadcast(rates), "currency")
        .withColumn("order_date", F.to_date("order_ts"))
        .withColumn("amount_usd", F.col("quantity") * F.col("unit_price") * F.col("rate_to_usd"))
    )
    daily = sales.groupBy("order_date").agg(
        F.countDistinct("order_id").alias("orders"),
        F.countDistinct("customer_id").alias("customers"),
        F.round(F.sum("amount_usd"), 2).alias("revenue_usd"),
    )
    by_category = sales.groupBy("order_date", "category").agg(
        F.round(F.sum("amount_usd"), 2).alias("revenue_usd"),
        F.sum("quantity").alias("units"),
    )
    for name, df in [("daily_revenue", daily), ("category_revenue", by_category)]:
        df.write.format("delta").mode("overwrite").save(path("gold", name))


def main() -> None:
    spark = get_spark("pipeline")
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    for step, fn in [("bronze", lambda: load_bronze(spark, batch_id)),
                     ("silver", lambda: build_silver(spark)),
                     ("gold", lambda: build_gold(spark))]:
        fn()
        print(f"{step:<7} done")

    print(f"\nBatch {batch_id}")
    for layer, table in [("silver", "orders"), ("silver", "order_items"), ("silver", "order_items_quarantine"),
                         ("silver", "events"), ("gold", "daily_revenue")]:
        print(f"  {layer}.{table:<24} {read(spark, layer, table).count():>7,} rows")


if __name__ == "__main__":
    main()
