"""Shared helpers: a local Spark session with Delta Lake, and table locations."""
from __future__ import annotations

from pathlib import Path

from delta import configure_spark_with_delta_pip
from pyspark.sql import DataFrame, SparkSession

LAB_DIR = Path(__file__).resolve().parent
RAW_DIR = LAB_DIR.parent / "data" / "output"
LAKE_DIR = LAB_DIR / "lakehouse"


def get_spark(app_name: str = "lab03") -> SparkSession:
    """Start (or reuse) a small local Spark session with Delta Lake enabled."""
    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[2]")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "4")      # the default of 200 is sized for clusters
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.showConsoleProgress", "false")
    )
    spark = configure_spark_with_delta_pip(builder).getOrCreate()   # downloads Delta JARs on first run
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def path(layer: str, table: str) -> str:
    """Location of a Delta table, e.g. path("silver", "orders")."""
    return str(LAKE_DIR / layer / table)


def read(spark: SparkSession, layer: str, table: str, version: int | None = None) -> DataFrame:
    """Read a Delta table, optionally as of an earlier version (time travel)."""
    reader = spark.read.format("delta")
    if version is not None:
        reader = reader.option("versionAsOf", version)
    return reader.load(path(layer, table))
