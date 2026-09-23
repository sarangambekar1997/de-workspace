# Apache Iceberg
> An open table format that brings ACID transactions, schema evolution, and time travel to any data lake.

**Prerequisites:** [Cloud Storage](cloud-storage.md) · [PySpark](../02-processing/pyspark-reference.md)

**Related:** [Databricks](../02-processing/databricks-reference.md) · [Snowflake](snowflake-reference.md) · [DE Concepts](../00-foundations/de-concepts.md) · [Glossary](../99-reference/glossary.md)

---

## Plain English

**What is Apache Iceberg?**

Imagine your data lake is a folder of Parquet files on S3. The problem: there's no "table" — just files. You can't do `UPDATE`, you can't roll back a bad write, and two jobs writing at the same time corrupt each other.

Iceberg is a **table format** that wraps those files with a metadata layer. It tracks which files belong to the table, what schema they have, and what changed when. The files stay on S3 — Iceberg just adds structure on top.

```
Without Iceberg:          With Iceberg:
s3://bucket/orders/       iceberg table "orders"
  2024-03-15.parquet        ├── metadata/ (schema, snapshots, history)
  2024-03-16.parquet        └── data/     (the same Parquet files)
  2024-03-17.parquet
  (just files — no table)   (a real table with ACID, history, evolution)
```

**Why Iceberg over Delta Lake?**
- Delta Lake is Databricks-native; Iceberg is truly open — Spark, Flink, Trino, Snowflake, and BigQuery all read it natively
- Choose Iceberg when your data sits in a multi-engine environment; Delta when you're all-in on Databricks

---

## Table of Contents

**Basic**
- [Core Concepts](#core-concepts)
- [Setup with PySpark](#setup-with-pyspark)
- [Creating and Writing Tables](#creating-and-writing-tables)
- [Reading Data](#reading-data)

**Intermediate**
- [Schema Evolution](#schema-evolution)
- [Partitioning](#partitioning)
- [Time Travel](#time-travel)
- [ACID Operations](#acid-operations)

**Advanced**
- [Table Maintenance](#table-maintenance)
- [Iceberg on AWS (Glue + Athena)](#iceberg-on-aws-glue--athena)
- [Iceberg vs Delta Lake vs Hudi](#iceberg-vs-delta-lake-vs-hudi)
- [Common Mistakes](#common-mistakes)

---

## Core Concepts

| Concept | Plain English |
|---------|--------------|
| **Table format** | A specification for how to organize data files and metadata so any engine can read the "table" | 
| **Snapshot** | A point-in-time version of the table — every write creates a new snapshot |
| **Manifest** | A file listing all data files in a snapshot with their statistics |
| **Catalog** | A service that maps table names to their metadata location (Hive Metastore, AWS Glue, Nessie, REST) |
| **Hidden partitioning** | Iceberg handles partition transforms automatically — no more `dt=2024-03-15` folder names in queries |
| **Metadata evolution** | Add, rename, or drop columns without rewriting data |

```
Iceberg metadata hierarchy:
  Table  (name → metadata pointer)
    └── Metadata file  (schema, partition spec, current snapshot)
          └── Snapshot (list of manifest files)
                └── Manifest (list of data files + stats)
                      └── Data file  (actual Parquet/ORC/Avro)
```

---

## Setup with PySpark

```python
# pip install pyspark apache-iceberg pyspark

from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("iceberg-demo") \
    .config("spark.jars.packages",
            "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0") \
    .config("spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .config("spark.sql.catalog.local",
            "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.local.type", "hadoop") \
    .config("spark.sql.catalog.local.warehouse", "/tmp/iceberg-warehouse") \
    .getOrCreate()
```

```python
# AWS Glue catalog (production setup)
spark = SparkSession.builder \
    .config("spark.sql.catalog.glue_catalog",
            "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.glue_catalog.warehouse",
            "s3://my-bucket/iceberg/") \
    .config("spark.sql.catalog.glue_catalog.catalog-impl",
            "org.apache.iceberg.aws.glue.GlueCatalog") \
    .config("spark.sql.catalog.glue_catalog.io-impl",
            "org.apache.iceberg.aws.s3.S3FileIO") \
    .getOrCreate()
```

---

## Creating and Writing Tables

```python
from pyspark.sql import functions as F

# Create an Iceberg table via SQL
spark.sql("""
    CREATE TABLE IF NOT EXISTS local.db.orders (
        order_id     STRING,
        customer_id  STRING,
        amount       DOUBLE,
        status       STRING,
        order_date   DATE
    )
    USING iceberg
    PARTITIONED BY (order_date)
    LOCATION '/tmp/iceberg-warehouse/db/orders'
    TBLPROPERTIES (
        'format-version'           = '2',
        'write.format.default'     = 'parquet',
        'write.target-file-size-bytes' = '134217728'  -- 128MB
    )
""")

# Write via DataFrame
df = spark.createDataFrame([
    ("ORD-001", "CUST-1", 99.99,  "placed",    "2024-03-15"),
    ("ORD-002", "CUST-2", 149.50, "shipped",   "2024-03-15"),
    ("ORD-003", "CUST-1", 29.00,  "delivered", "2024-03-16"),
], ["order_id", "customer_id", "amount", "status", "order_date"])

df = df.withColumn("order_date", F.col("order_date").cast("date"))

# Append (default)
df.writeTo("local.db.orders").append()

# Overwrite a specific partition
df.writeTo("local.db.orders") \
  .overwritePartitions()

# Full overwrite
df.writeTo("local.db.orders").overwrite(F.lit(True))
```

---

## Reading Data

```python
# Read the current snapshot
df = spark.table("local.db.orders")
df.show()

# Via SQL
spark.sql("SELECT * FROM local.db.orders WHERE status = 'placed'").show()

# Check table metadata
spark.sql("DESCRIBE EXTENDED local.db.orders").show(truncate=False)

# Show snapshots (history)
spark.sql("SELECT * FROM local.db.orders.snapshots").show()

# Show data files
spark.sql("SELECT * FROM local.db.orders.files").show()

# Show history
spark.sql("SELECT * FROM local.db.orders.history").show()
```

---

## Schema Evolution

```python
# Add a column (non-breaking)
spark.sql("ALTER TABLE local.db.orders ADD COLUMN shipping_cost DOUBLE")

# Rename a column
spark.sql("ALTER TABLE local.db.orders RENAME COLUMN shipping_cost TO shipping_fee")

# Change a column type (only widening types: int → long, float → double)
spark.sql("ALTER TABLE local.db.orders ALTER COLUMN amount TYPE DECIMAL(12, 2)")

# Drop a column (data still in files, just not exposed in schema)
spark.sql("ALTER TABLE local.db.orders DROP COLUMN shipping_fee")

# After schema changes, old data files still work — Iceberg handles nulls for
# missing columns automatically

# Schema evolution rules:
# ✓  Adding columns      — always safe
# ✓  Dropping columns    — safe (data stays, not visible)
# ✓  Renaming columns    — safe (tracked by column ID, not name)
# ✓  Widening types      — safe (int→long, float→double)
# ✗  Narrowing types     — NOT allowed (double→float loses precision)
# ✗  Changing semantics  — NOT safe (renaming to mean something different)
```

---

## Partitioning

Iceberg's hidden partitioning is one of its best features — no `WHERE dt='2024-03-15'` needed.

```python
# Partition transforms — Iceberg applies these automatically at write time
spark.sql("""
    CREATE TABLE local.db.events (
        event_id   STRING,
        user_id    STRING,
        event_type STRING,
        event_ts   TIMESTAMP,
        amount     DOUBLE
    )
    USING iceberg
    PARTITIONED BY (
        days(event_ts),        -- partition by day from a timestamp
        bucket(16, user_id)    -- hash into 16 buckets (for high-cardinality cols)
    )
""")

# Available transforms:
# year(ts)      → YYYY
# month(ts)     → YYYY-MM
# days(ts)      → YYYY-MM-DD   (most common)
# hours(ts)     → YYYY-MM-DD-HH
# bucket(N, col) → hash into N buckets
# truncate(N, col) → string prefix or integer truncation

# Writing — Iceberg handles partitioning transparently
df.writeTo("local.db.events").append()

# Querying — no partition filter needed in WHERE; Iceberg prunes automatically
spark.sql("""
    SELECT COUNT(*) FROM local.db.events
    WHERE event_ts BETWEEN '2024-03-01' AND '2024-03-15'
""").show()
# Iceberg reads only the day=2024-03-01 through day=2024-03-15 partitions

# Evolve the partition spec without rewriting data
spark.sql("ALTER TABLE local.db.events ADD PARTITION FIELD hours(event_ts)")
spark.sql("ALTER TABLE local.db.events DROP PARTITION FIELD days(event_ts)")
```

---

## Time Travel

```python
# Query a specific snapshot
spark.sql("""
    SELECT * FROM local.db.orders
    VERSION AS OF 1234567890  -- snapshot ID
""").show()

# Query at a specific timestamp
spark.sql("""
    SELECT * FROM local.db.orders
    TIMESTAMP AS OF '2024-03-15 12:00:00'
""").show()

# Via DataFrame reader
df = spark.read \
    .option("snapshot-id", "1234567890") \
    .table("local.db.orders")

df = spark.read \
    .option("as-of-timestamp", "1710504000000") \  # milliseconds since epoch
    .table("local.db.orders")

# Rollback to a previous snapshot
spark.sql("CALL local.system.rollback_to_snapshot('db.orders', 1234567890)")

# Rollback to a timestamp
spark.sql("CALL local.system.rollback_to_timestamp('db.orders', TIMESTAMP '2024-03-14 00:00:00')")
```

---

## ACID Operations

```python
# MERGE (upsert) — insert new, update existing
spark.sql("""
    MERGE INTO local.db.orders t
    USING updates s ON t.order_id = s.order_id
    WHEN MATCHED THEN UPDATE SET t.status = s.status, t.amount = s.amount
    WHEN NOT MATCHED THEN INSERT *
""")

# UPDATE
spark.sql("""
    UPDATE local.db.orders
    SET status = 'cancelled'
    WHERE order_date < '2024-01-01' AND status = 'placed'
""")

# DELETE
spark.sql("""
    DELETE FROM local.db.orders
    WHERE status = 'cancelled' AND order_date < '2023-01-01'
""")

# Copy-on-write (default) vs Merge-on-read:
# Copy-on-write: rewrites entire files on every update/delete — fast reads, slow writes
# Merge-on-read: writes delete files; merges at read time — fast writes, slower reads
spark.sql("""
    ALTER TABLE local.db.orders
    SET TBLPROPERTIES ('write.delete.mode' = 'merge-on-read')
""")
```

---

## Table Maintenance

```python
# Expire old snapshots (reclaim storage)
spark.sql("""
    CALL local.system.expire_snapshots(
        table         => 'db.orders',
        older_than    => TIMESTAMP '2024-03-01 00:00:00',
        retain_last   => 5
    )
""")

# Remove orphan files (files not referenced by any snapshot)
spark.sql("""
    CALL local.system.remove_orphan_files(table => 'db.orders')
""")

# Compact small files (rewrite into larger files)
spark.sql("""
    CALL local.system.rewrite_data_files(
        table   => 'db.orders',
        options => map('target-file-size-bytes', '134217728')
    )
""")

# Rewrite manifests (improves planning performance on large tables)
spark.sql("""
    CALL local.system.rewrite_manifests(table => 'db.orders')
""")
```

---

## Iceberg on AWS (Glue + Athena)

```python
# AWS Glue Catalog + S3 + Athena — no Spark cluster needed for queries

# Create table via Glue (in AWS console or boto3)
import boto3

glue = boto3.client("glue", region_name="us-east-1")
glue.create_table(
    DatabaseName="mydb",
    TableInput={
        "Name": "orders",
        "StorageDescriptor": {
            "Location": "s3://my-bucket/iceberg/orders/",
            "InputFormat":  "org.apache.iceberg.mr.hive.HiveIcebergInputFormat",
            "OutputFormat": "org.apache.iceberg.mr.hive.HiveIcebergOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.iceberg.mr.hive.HiveIcebergSerDe"},
        },
        "Parameters": {"table_type": "ICEBERG"},
    }
)

# Query in Athena (after table registered in Glue)
# SELECT * FROM mydb.orders WHERE order_date >= DATE '2024-03-01'

# Athena time travel
# SELECT * FROM mydb.orders FOR SYSTEM_TIME AS OF TIMESTAMP '2024-03-15 12:00:00'
```

---

## Iceberg vs Delta Lake vs Hudi

| | Apache Iceberg | Delta Lake | Apache Hudi |
|-|----------------|------------|-------------|
| **Creator** | Netflix/Apple → Apache | Databricks | Uber |
| **Open standard** | Yes | Yes (open source) | Yes |
| **Best engine** | Any (Spark, Trino, Flink) | Databricks/Spark | Spark |
| **ACID** | Yes | Yes | Yes |
| **Time travel** | Yes | Yes | Yes |
| **Schema evolution** | Excellent (by column ID) | Good | Good |
| **Partition evolution** | Yes (no rewrite) | Limited | Limited |
| **Hidden partitioning** | Yes | No | No |
| **Streaming** | Good (via Flink) | Excellent | Excellent |
| **Multi-engine** | Best | Good | Fair |
| **AWS native** | Glue, Athena, EMR | EMR | EMR |
| **Choose when** | Multi-engine, cloud-agnostic | All-in on Databricks | Upsert-heavy, CDC workloads |

---

## Common Mistakes

```
1. Forgetting to configure a catalog
   Problem: Iceberg tables need a catalog — without one, nothing persists
   Fix:     Always configure Hive Metastore, AWS Glue, or Nessie catalog in SparkSession

2. Not running table maintenance
   Problem: snapshots accumulate, storage balloons, planning slows down
   Fix:     Schedule weekly: expire_snapshots + remove_orphan_files + rewrite_data_files

3. Using year() or month() partition transforms on high-query-frequency tables
   Problem: year(ts) creates partitions with millions of files — too coarse
   Fix:     Use days(ts) for daily-batch tables, hours(ts) for streaming tables

4. Over-partitioning with bucket()
   Problem: bucket(1000, user_id) creates 1000 files per write — too many small files
   Fix:     Start with bucket(16) or bucket(32); 128MB target file size

5. Mixing Iceberg V1 and V2 features
   Problem: V2 adds row-level deletes (needed for MERGE/DELETE/UPDATE)
   Fix:     Always create tables with 'format-version' = '2'

6. Skipping OPTIMIZE after heavy upserts
   Problem: merge-on-read tables accumulate delete files → slower reads over time
   Fix:     Run rewrite_data_files after bulk upserts to compact
```

---

## Interview Questions

**Q: What problem does Iceberg solve that raw Parquet files on S3 don't?**
A: Raw Parquet has no table concept — no ACID, no schema enforcement, no concurrent write safety, no history. Iceberg adds a metadata layer (snapshots, manifests) that makes S3 files into a real table with transactions, time travel, and schema evolution, while keeping the files open-format and readable by any engine.

**Q: What is hidden partitioning and why does it matter?**
A: In Hive/traditional partitioning, the query must include a filter on the partition column (`WHERE dt='2024-03-15'`) or it scans everything. In Iceberg, you define partition transforms (`days(event_ts)`) and Iceberg applies them transparently — the query just filters on `event_ts` and Iceberg handles pruning. This prevents accidental full-table scans.

**Q: How does Iceberg handle schema evolution without rewriting data?**
A: Iceberg tracks columns by a stable integer ID, not by name. When you rename a column, the ID stays the same — old files still map to the right column. New columns default to NULL for old files. Type changes are allowed only for safe widenings (int → long).

**Q: What is copy-on-write vs merge-on-read?**
A: Copy-on-write rewrites entire data files when rows are updated/deleted — reads are fast because there's only one file per row, but writes are expensive. Merge-on-read writes small delete/delta files alongside data files and merges them at read time — writes are fast, reads are slightly slower. Choose copy-on-write for read-heavy, update-infrequent tables; merge-on-read for frequent upserts.

---

**Previous:** [Databricks](../02-processing/databricks-reference.md) · **Next:** [Kafka](../04-streaming/kafka-reference.md) · **Back to:** [Index](../README.md)
