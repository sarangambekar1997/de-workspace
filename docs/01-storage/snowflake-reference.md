# Snowflake Reference
> From first query to production-grade cloud data warehouse patterns.

---

## Table of Contents

**Basics**
- [Architecture](#architecture)
- [Key Concepts](#key-concepts)
- [Databases, Schemas & Tables](#databases-schemas--tables)
- [Data Types](#data-types)
- [Querying Data](#querying-data)

**Intermediate**
- [Loading Data](#loading-data)
- [Virtual Warehouses](#virtual-warehouses)
- [Semi-Structured Data](#semi-structured-data)
- [Time Travel](#time-travel)
- [Cloning](#cloning)
- [Streams & Tasks](#streams--tasks)

**Advanced**
- [Query Performance](#query-performance)
- [Clustering Keys](#clustering-keys)
- [Cost Management](#cost-management)
- [Access Control & RBAC](#access-control--rbac)
- [Snowflake-Specific SQL](#snowflake-specific-sql)

---

## Architecture

Snowflake separates storage, compute, and cloud services into three independent layers.

```
┌─────────────────────────────────────────────┐
│          Cloud Services Layer               │
│  (authentication, optimizer, metadata,      │
│   security, query compilation)              │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────┴───────────────────────────┐
│          Query Processing Layer             │
│   Warehouse A    Warehouse B    Warehouse C │
│   (XS)           (M)            (L)         │
│   own CPU/RAM    own CPU/RAM    own CPU/RAM │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────┴───────────────────────────┐
│          Database Storage Layer             │
│   (compressed columnar files in S3/Azure   │
│    Blob / GCS — decoupled from compute)    │
└─────────────────────────────────────────────┘
```

**Key insight:** compute (virtual warehouses) and storage are completely decoupled.
- Multiple warehouses can read the same data simultaneously
- Warehouses can be paused without losing data
- Storage costs and compute costs scale independently

---

## Key Concepts

| Concept | What it is |
|---------|-----------|
| **Virtual Warehouse** | A cluster of compute nodes (CPU + RAM); runs queries; billed per second when active |
| **Credit** | Snowflake's billing unit; 1 credit = 1 hour of 1 XS warehouse |
| **Micro-partition** | Immutable ~50–500 MB columnar files; Snowflake's internal storage unit |
| **Metadata Store** | Stores min/max values, row counts per micro-partition — enables pruning |
| **Result Cache** | Query results cached 24h; identical query returns instantly at zero cost |
| **Time Travel** | Access historical data up to 90 days back |
| **Fail-safe** | 7-day disaster recovery window (not queryable — Snowflake support only) |
| **Stage** | Named location for data files: internal (Snowflake-managed) or external (your S3/GCS/ADLS) |
| **Snowpipe** | Continuous, serverless ingestion from a stage — triggers on file arrival |
| **Stream** | CDC table — tracks inserts/updates/deletes since the last consumption |
| **Task** | Scheduled SQL or stored procedure; Snowflake's built-in scheduler |
| **Share** | Share live data with another Snowflake account without copying it |

---

## Databases, Schemas & Tables

```sql
-- Database
CREATE DATABASE analytics;
USE DATABASE analytics;

-- Schema
CREATE SCHEMA analytics.staging;
CREATE SCHEMA analytics.marts;
USE SCHEMA analytics.staging;

-- Fully qualified name: database.schema.table
SELECT * FROM analytics.marts.dim_customer;

-- Table
CREATE TABLE staging.orders (
    order_id     VARCHAR(36)    NOT NULL,
    customer_id  INTEGER        NOT NULL,
    amount       NUMBER(12, 2),
    status       VARCHAR(20),
    created_at   TIMESTAMP_NTZ,           -- no timezone
    updated_at   TIMESTAMP_LTZ            -- local timezone
);

-- Create table from query
CREATE TABLE marts.order_summary AS
SELECT DATE(created_at) AS order_date, SUM(amount) AS revenue
FROM   staging.orders
GROUP  BY 1;

-- Transient table — no fail-safe (lower cost; use for staging/temp data)
CREATE TRANSIENT TABLE staging.raw_orders (...);

-- Temporary table — session-scoped, auto-dropped
CREATE TEMPORARY TABLE temp_work AS SELECT ...;

-- External table — query files directly on S3 without loading
CREATE EXTERNAL TABLE raw.orders_ext (
    order_id  VARCHAR AS (VALUE:order_id::VARCHAR),
    amount    FLOAT   AS (VALUE:amount::FLOAT)
)
WITH LOCATION = @my_s3_stage/orders/
FILE_FORMAT = (TYPE = PARQUET);
```

---

## Data Types

| Category | Type | Notes |
|----------|------|-------|
| Numeric | `NUMBER(p,s)`, `INTEGER`, `BIGINT`, `FLOAT`, `DOUBLE` | `NUMBER` is exact; use for money |
| String | `VARCHAR(n)`, `STRING`, `TEXT` | All stored as UTF-8; max 16 MB |
| Date/Time | `DATE`, `TIME`, `TIMESTAMP_NTZ`, `TIMESTAMP_LTZ`, `TIMESTAMP_TZ` | NTZ = no timezone, LTZ = local, TZ = with offset |
| Boolean | `BOOLEAN` | `TRUE`, `FALSE`, `NULL` |
| Semi-structured | `VARIANT`, `ARRAY`, `OBJECT` | Store any JSON/XML/Avro |
| Geospatial | `GEOGRAPHY`, `GEOMETRY` | For spatial queries |

```sql
-- VARIANT — stores any JSON value
CREATE TABLE events (
    event_id  INTEGER,
    payload   VARIANT    -- can hold any JSON structure
);

INSERT INTO events VALUES (1, PARSE_JSON('{"type":"click","page":"home","user":42}'));

-- Query VARIANT fields
SELECT payload:type::STRING      AS event_type,
       payload:user::INTEGER     AS user_id,
       payload:page::STRING      AS page
FROM   events;
```

---

## Querying Data

Snowflake supports standard SQL plus many extensions. All SQL reference patterns apply here.

```sql
-- Standard SELECT (see sql-reference.md for full SQL coverage)
SELECT order_id, amount, status
FROM   staging.orders
WHERE  created_at >= DATEADD(day, -7, CURRENT_TIMESTAMP())
ORDER  BY created_at DESC
LIMIT  100;

-- Snowflake-specific: QUALIFY — filter window function results inline
SELECT name, dept, salary,
    RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS rnk
FROM employees
QUALIFY rnk <= 3;    -- top 3 per department without a subquery

-- PIVOT
SELECT *
FROM   monthly_revenue
PIVOT (SUM(revenue) FOR month IN ('Jan', 'Feb', 'Mar')) AS p;

-- UNPIVOT
SELECT product, month, revenue
FROM   quarterly_data
UNPIVOT (revenue FOR month IN (jan, feb, mar));

-- FLATTEN — expand ARRAY or OBJECT into rows
SELECT f.value::STRING AS tag
FROM   products,
       LATERAL FLATTEN(INPUT => tags) f;

-- SAMPLE — random sample
SELECT * FROM orders SAMPLE (10);            -- 10% random
SELECT * FROM orders SAMPLE (1000 ROWS);     -- exactly 1000 rows
```

---

## Loading Data

### Stages

```sql
-- Internal stage — Snowflake-managed storage
CREATE STAGE my_internal_stage
    FILE_FORMAT = (TYPE = CSV FIELD_OPTIONALLY_ENCLOSED_BY = '"' SKIP_HEADER = 1);

-- External stage — your S3 bucket
CREATE STAGE my_s3_stage
    URL = 's3://my-bucket/data/'
    CREDENTIALS = (AWS_KEY_ID = '...' AWS_SECRET_KEY = '...')
    FILE_FORMAT = (TYPE = PARQUET);

-- List files in a stage
LIST @my_s3_stage;

-- Upload a local file to internal stage (SnowSQL CLI)
PUT file:///local/path/orders.csv @my_internal_stage;
```

### COPY INTO — batch load

```sql
-- Load from stage into table
COPY INTO staging.orders
FROM @my_s3_stage/orders/2024/03/
FILE_FORMAT = (TYPE = PARQUET)
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = 'SKIP_FILE';    -- ABORT_STATEMENT | CONTINUE | SKIP_FILE

-- Load CSV with options
COPY INTO staging.customers
FROM @my_s3_stage/customers/
FILE_FORMAT = (
    TYPE = CSV
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    DATE_FORMAT = 'YYYY-MM-DD'
    TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS'
)
PURGE = TRUE;     -- delete files from stage after successful load

-- Validate before loading (dry run)
COPY INTO staging.orders
FROM @my_s3_stage/orders/
VALIDATION_MODE = 'RETURN_ERRORS';

-- Check load history
SELECT *
FROM   information_schema.load_history
WHERE  table_name = 'ORDERS'
ORDER  BY last_load_time DESC
LIMIT  10;
```

### Snowpipe — continuous ingestion

```sql
-- Create a pipe pointing to a stage and target table
CREATE PIPE orders_pipe
    AUTO_INGEST = TRUE   -- triggered by S3 event notifications
AS
COPY INTO staging.orders
FROM @my_s3_stage/orders/
FILE_FORMAT = (TYPE = PARQUET);

-- Check pipe status
SELECT SYSTEM$PIPE_STATUS('orders_pipe');

-- Manually trigger for specific files
ALTER PIPE orders_pipe REFRESH
    PREFIX = 'orders/2024/03/15/';
```

---

## Virtual Warehouses

```sql
-- Create a warehouse
CREATE WAREHOUSE analytics_wh
    WAREHOUSE_SIZE = 'MEDIUM'         -- XS, S, M, L, XL, 2XL, 3XL, 4XL, 5XL, 6XL
    AUTO_SUSPEND = 120                -- auto-suspend after 120 seconds of inactivity
    AUTO_RESUME = TRUE                -- auto-resume when a query arrives
    MAX_CLUSTER_COUNT = 3             -- multi-cluster: scale out to 3 clusters
    MIN_CLUSTER_COUNT = 1             -- scale back to 1 when load drops
    SCALING_POLICY = 'STANDARD';      -- STANDARD | ECONOMY

-- Use a warehouse
USE WAREHOUSE analytics_wh;

-- Resize on the fly (takes effect immediately for new queries)
ALTER WAREHOUSE analytics_wh SET WAREHOUSE_SIZE = 'LARGE';

-- Suspend / resume manually
ALTER WAREHOUSE analytics_wh SUSPEND;
ALTER WAREHOUSE analytics_wh RESUME;

-- Warehouse sizes and credits/hour
-- XS=1  S=2  M=4  L=8  XL=16  2XL=32  3XL=64  4XL=128
```

### Multi-cluster warehouses

Multi-cluster allows a warehouse to spin up additional clusters when queued queries exceed a threshold. Solves concurrency bottlenecks without resizing.

```sql
CREATE WAREHOUSE reporting_wh
    WAREHOUSE_SIZE = 'MEDIUM'
    MAX_CLUSTER_COUNT = 5     -- up to 5 parallel clusters
    MIN_CLUSTER_COUNT = 1     -- always at least 1 running
    SCALING_POLICY = 'ECONOMY';  -- wait longer before spinning up extra cluster
                                 -- STANDARD scales aggressively
```

---

## Semi-Structured Data

Snowflake's `VARIANT` type stores any JSON, Avro, Parquet, or XML natively.

```sql
-- Dot notation to traverse JSON
SELECT
    payload:user_id::INTEGER         AS user_id,
    payload:event.type::STRING       AS event_type,
    payload:items[0].sku::STRING     AS first_sku,   -- array index
    payload:metadata:source::STRING  AS source
FROM events;

-- FLATTEN — turn array into rows
SELECT
    order_id,
    f.value:sku::STRING     AS sku,
    f.value:quantity::INT   AS qty
FROM orders,
     LATERAL FLATTEN(INPUT => line_items) f;

-- Check if a key exists
SELECT * FROM events WHERE payload:user_id IS NOT NULL;

-- Parse JSON string into VARIANT
SELECT PARSE_JSON('{"key": "value"}'):key::STRING;

-- Convert VARIANT back to string
SELECT payload::STRING FROM events;

-- Build a VARIANT from columns
SELECT OBJECT_CONSTRUCT('id', id, 'name', name) AS json_row
FROM customers;
```

---

## Time Travel

Query, clone, or restore data from any point in the past (up to 90 days for Enterprise edition).

```sql
-- Query table as it was 1 hour ago
SELECT * FROM orders AT (OFFSET => -3600);   -- seconds

-- Query at a specific timestamp
SELECT * FROM orders AT (TIMESTAMP => '2024-03-14 09:00:00'::TIMESTAMP);

-- Query before a specific statement executed
SELECT * FROM orders BEFORE (STATEMENT => '01b48fd2-0001-b7b8-...');

-- Restore a dropped table
UNDROP TABLE staging.orders;

-- Restore a table to a prior state (create from time travel, then swap)
CREATE OR REPLACE TABLE orders_restored
    CLONE orders AT (TIMESTAMP => '2024-03-14 00:00:00'::TIMESTAMP);

-- Set retention period (default 1 day for Standard, up to 90 for Enterprise)
ALTER TABLE orders SET DATA_RETENTION_TIME_IN_DAYS = 7;
```

---

## Cloning

Zero-copy cloning creates an independent copy of a table, schema, or database instantly — no data is physically copied until one side modifies it.

```sql
-- Clone a table (instant, zero storage cost initially)
CREATE TABLE orders_backup CLONE orders;

-- Clone a schema (clones all objects within it)
CREATE SCHEMA staging_backup CLONE staging;

-- Clone a database
CREATE DATABASE analytics_dev CLONE analytics;

-- Clone at a point in time (useful for dev/test environments)
CREATE DATABASE analytics_dev CLONE analytics
    AT (TIMESTAMP => '2024-03-01 00:00:00'::TIMESTAMP);
```

> Cloning is the standard way to create dev/test environments in Snowflake. Clone production, work in the clone, discard when done — no cost until data diverges.

---

## Streams & Tasks

### Streams — CDC on tables

A stream tracks all DML changes (INSERT, UPDATE, DELETE) to a table since it was last consumed.

```sql
-- Create a stream on a source table
CREATE STREAM orders_stream ON TABLE staging.raw_orders;

-- Query the stream — see what changed
SELECT *,
    METADATA$ACTION,        -- INSERT or DELETE
    METADATA$ISUPDATE,      -- true if part of an UPDATE (appears as DELETE + INSERT)
    METADATA$ROW_ID
FROM orders_stream;

-- Consume the stream in a merge (marks it as consumed)
MERGE INTO marts.orders AS target
USING (
    SELECT * FROM orders_stream WHERE METADATA$ACTION = 'INSERT'
) AS source ON target.order_id = source.order_id
WHEN MATCHED THEN UPDATE SET target.amount = source.amount,
                              target.status = source.status
WHEN NOT MATCHED THEN INSERT VALUES (source.order_id, source.amount, source.status);
-- After this executes, orders_stream resets — only shows new changes going forward

-- Check if a stream has unconsumed data
SELECT SYSTEM$STREAM_HAS_DATA('orders_stream');
```

### Tasks — scheduled SQL

```sql
-- Create a task that runs every hour
CREATE TASK refresh_summary
    WAREHOUSE = analytics_wh
    SCHEDULE = 'USING CRON 0 * * * * UTC'
AS
INSERT INTO marts.hourly_summary
SELECT DATE_TRUNC('hour', created_at) AS hour,
       COUNT(*) AS orders, SUM(amount) AS revenue
FROM   staging.orders
WHERE  created_at >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP  BY 1;

-- Tasks start suspended — resume to activate
ALTER TASK refresh_summary RESUME;

-- Task chain — run task B after task A completes
CREATE TASK transform_task
    AFTER extract_task        -- no SCHEDULE needed, triggered by parent
AS
    CALL transform_proc();

-- View task history
SELECT *
FROM   TABLE(information_schema.task_history())
ORDER  BY scheduled_time DESC
LIMIT  20;
```

---

## Query Performance

### Query Profile

The most important performance tool. Open any query result → Query Profile to see:
- Execution time per node
- Bytes scanned vs pruned
- Spill to disk (means warehouse is too small for the query)
- The most expensive step

### Micro-partition pruning

Snowflake stores metadata (min/max values, row count) for each micro-partition. Filters on those columns skip entire partitions without reading them.

```sql
-- This can skip most partitions if created_at has good min/max range
SELECT * FROM orders WHERE created_at >= '2024-03-01';

-- SHOW TABLES includes partition stats
SHOW TABLES LIKE 'orders';

-- Check how well a query prunes
SELECT * FROM orders WHERE order_id = 'abc123';
-- Check Query Profile: "Partitions scanned" vs "Partitions total"
-- Good: 1/10000 partitions scanned
-- Bad:  10000/10000 partitions scanned (full scan — consider clustering)
```

### Result cache

```sql
-- Identical query returns instantly from cache (0 credits used)
SELECT COUNT(*) FROM orders;
-- Run again — "result reused" in Query Profile

-- Disable result cache for benchmarking
ALTER SESSION SET USE_CACHED_RESULT = FALSE;

-- Cache is shared across users for the same warehouse
-- Invalidated when underlying table changes
```

---

## Clustering Keys

When queries consistently filter on a high-cardinality column but partition pruning is poor, define a clustering key. Snowflake will physically reorganize micro-partitions so filtered ranges are co-located.

```sql
-- Add a clustering key
ALTER TABLE orders CLUSTER BY (DATE(created_at));

-- Multi-column clustering
ALTER TABLE events CLUSTER BY (user_id, DATE(event_time));

-- Check clustering depth (lower = better; >6 means recluster)
SELECT SYSTEM$CLUSTERING_INFORMATION('orders', '(DATE(created_at))');

-- Manual reclustering (usually automatic in Enterprise)
ALTER TABLE orders RECLUSTER;

-- Drop a clustering key
ALTER TABLE orders DROP CLUSTERING KEY;
```

> Use clustering only when:
> - The table is very large (>1 TB)
> - Queries consistently filter on the same column(s)
> - Query Profile shows poor partition pruning

---

## Cost Management

```sql
-- Credit usage by warehouse (last 30 days)
SELECT warehouse_name,
       SUM(credits_used) AS total_credits,
       ROUND(SUM(credits_used) * 3.0, 2) AS estimated_usd   -- ~$3/credit on-demand
FROM   snowflake.account_usage.warehouse_metering_history
WHERE  start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
GROUP  BY 1
ORDER  BY 2 DESC;

-- Query cost — bytes scanned and execution time
SELECT query_id, query_text, warehouse_name,
       execution_time / 1000 AS seconds,
       bytes_scanned / 1e9   AS gb_scanned,
       credits_used_cloud_services
FROM   snowflake.account_usage.query_history
WHERE  start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP())
ORDER  BY credits_used_cloud_services DESC
LIMIT  20;

-- Storage costs
SELECT TABLE_SCHEMA, TABLE_NAME,
       ROUND(ACTIVE_BYTES / 1e9, 2)         AS active_gb,
       ROUND(TIME_TRAVEL_BYTES / 1e9, 2)    AS time_travel_gb,
       ROUND(FAILSAFE_BYTES / 1e9, 2)       AS failsafe_gb
FROM   snowflake.account_usage.table_storage_metrics
ORDER  BY active_gb DESC
LIMIT  20;
```

### Cost reduction patterns

```sql
-- 1. Ensure warehouses auto-suspend
ALTER WAREHOUSE my_wh SET AUTO_SUSPEND = 60;   -- 60 second idle timeout

-- 2. Use transient tables for staging (no fail-safe cost)
CREATE TRANSIENT TABLE staging.raw_orders (...);

-- 3. Reduce time travel on large tables that don't need it
ALTER TABLE staging.raw_orders SET DATA_RETENTION_TIME_IN_DAYS = 0;

-- 4. Query result cache is free — don't disable it in production

-- 5. Use COPY INTO over INSERT for bulk loads (more efficient)

-- 6. Right-size warehouses — profile queries before scaling up
```

---

## Access Control & RBAC

Snowflake uses role-based access control (RBAC). Everything is granted to a role, and users are assigned roles.

```sql
-- Create roles
CREATE ROLE analyst;
CREATE ROLE data_engineer;
CREATE ROLE loader;

-- Grant privileges to roles
GRANT USAGE ON DATABASE analytics          TO ROLE analyst;
GRANT USAGE ON SCHEMA analytics.marts     TO ROLE analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics.marts TO ROLE analyst;
GRANT SELECT ON FUTURE TABLES IN SCHEMA analytics.marts TO ROLE analyst;

GRANT ALL ON SCHEMA analytics.staging TO ROLE data_engineer;
GRANT USAGE ON WAREHOUSE analytics_wh  TO ROLE analyst;
GRANT USAGE ON WAREHOUSE transform_wh  TO ROLE data_engineer;

-- Create user and assign role
CREATE USER alice
    PASSWORD = 'strong_password'
    DEFAULT_ROLE = analyst
    DEFAULT_WAREHOUSE = analytics_wh;

GRANT ROLE analyst TO USER alice;

-- Role hierarchy — grant role to another role
GRANT ROLE analyst TO ROLE data_engineer;   -- engineers inherit analyst privileges

-- Show grants
SHOW GRANTS TO ROLE analyst;
SHOW GRANTS TO USER alice;
SHOW GRANTS ON TABLE orders;
```

---

## Snowflake-Specific SQL

```sql
-- QUALIFY — filter window results without a subquery
SELECT *, RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS rnk
FROM employees
QUALIFY rnk = 1;    -- highest earner per department

-- IFF — shorthand CASE WHEN for single condition
SELECT IFF(amount > 1000, 'large', 'small') AS order_size FROM orders;

-- ZEROIFNULL / NULLIFZERO
SELECT ZEROIFNULL(revenue) FROM report;   -- NULL → 0
SELECT NULLIFZERO(quantity) FROM items;  -- 0 → NULL

-- DATE_TRUNC
SELECT DATE_TRUNC('month', created_at) AS month, COUNT(*) FROM orders GROUP BY 1;
SELECT DATE_TRUNC('week',  event_time) AS week,  COUNT(*) FROM events  GROUP BY 1;

-- DATEADD / DATEDIFF
SELECT DATEADD('day', -7, CURRENT_DATE());
SELECT DATEDIFF('day', hire_date, CURRENT_DATE()) AS tenure_days FROM employees;

-- TO_CHAR — format a date as string
SELECT TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') FROM orders;

-- TRY_CAST — safe cast, returns NULL on failure
SELECT TRY_CAST(raw_amount AS NUMBER(12,2)) FROM raw_data;

-- GENERATOR — generate a sequence of rows (useful for date spine)
SELECT DATEADD(day, SEQ4(), '2024-01-01'::DATE) AS cal_date
FROM   TABLE(GENERATOR(ROWCOUNT => 365));

-- LISTAGG — concatenate values within a group
SELECT dept, LISTAGG(name, ', ') WITHIN GROUP (ORDER BY name) AS employees
FROM   employees
GROUP  BY dept;

-- ARRAY_AGG and OBJECT_AGG
SELECT dept,
    ARRAY_AGG(name)        AS name_array,
    OBJECT_AGG(name, salary) AS name_salary_map
FROM employees
GROUP BY dept;
```
