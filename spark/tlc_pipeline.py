"""NYC TLC yellow-taxi profiling and idempotent curated aggregates.

Runs with local PySpark or as an AWS Glue Spark script. Input may be local
Parquet files or S3 URIs accessible to the Spark runtime.
"""

import argparse
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import NumericType


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def profile(frame):
    """Run distributed null counts and basic numeric statistics."""
    expressions = [F.count(F.lit(1)).alias("rows")]
    for field in frame.schema.fields:
        col = F.col(f"`{field.name.replace('`', '``')}`")
        expressions.append(F.sum(F.when(col.isNull(), 1).otherwise(0)).alias(f"{field.name}__nulls"))
        if isinstance(field.dataType, NumericType):
            expressions.extend([
                F.min(col).alias(f"{field.name}__min"),
                F.max(col).alias(f"{field.name}__max"),
                F.avg(col).alias(f"{field.name}__avg"),
            ])
    stats = frame.agg(*expressions).first().asDict()
    columns = []
    for field in frame.schema.fields:
        item = {"name": field.name, "dtype": field.dataType.simpleString(),
                "null_count": stats[f"{field.name}__nulls"]}
        if isinstance(field.dataType, NumericType):
            item["min"] = _json_value(stats[f"{field.name}__min"])
            item["max"] = _json_value(stats[f"{field.name}__max"])
            item["avg"] = _json_value(stats[f"{field.name}__avg"])
        columns.append(item)
    return {"rows": stats["rows"], "partitions": frame.rdd.getNumPartitions(), "columns": columns}


def aggregate(frame, year: int):
    required = {"tpep_pickup_datetime", "PULocationID", "fare_amount", "total_amount"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing TLC fields: {', '.join(sorted(missing))}")
    trips = (
        frame.select(
            F.to_date("tpep_pickup_datetime").alias("pickup_date"),
            F.col("PULocationID").cast("integer").alias("pickup_zone_id"),
            F.col("fare_amount").cast("double").alias("fare_amount"),
            F.col("total_amount").cast("double").alias("total_amount"),
        )
        .where(F.year("pickup_date") == year)
        .where(F.col("pickup_zone_id").isNotNull())
    )
    daily = trips.groupBy("pickup_date").agg(
        F.count("*").alias("trip_count"),
        F.avg("fare_amount").alias("avg_fare_amount"),
        F.avg("total_amount").alias("avg_total_amount"),
    )
    zones = trips.groupBy("pickup_zone_id").agg(
        F.count("*").alias("trip_count"),
        F.avg("fare_amount").alias("avg_fare_amount"),
        F.avg("total_amount").alias("avg_total_amount"),
    )
    return daily, zones


def publish(daily, zones, year: int, database_url: str):
    """Stream only the small aggregate result to PostgreSQL in one transaction."""
    import psycopg

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS curated")
            cursor.execute("""CREATE TABLE IF NOT EXISTS curated.tlc_daily (
                pickup_date date PRIMARY KEY, trip_count bigint NOT NULL,
                avg_fare_amount double precision, avg_total_amount double precision)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS curated.tlc_pickup_zone (
                service_year integer NOT NULL, pickup_zone_id integer NOT NULL,
                trip_count bigint NOT NULL, avg_fare_amount double precision,
                avg_total_amount double precision,
                PRIMARY KEY (service_year, pickup_zone_id))""")
            cursor.execute("DELETE FROM curated.tlc_daily WHERE pickup_date >= %s AND pickup_date < %s",
                           (date(year, 1, 1), date(year + 1, 1, 1)))
            cursor.execute("DELETE FROM curated.tlc_pickup_zone WHERE service_year = %s", (year,))
            cursor.executemany(
                "INSERT INTO curated.tlc_daily VALUES (%s, %s, %s, %s)",
                ((row.pickup_date, row.trip_count, row.avg_fare_amount, row.avg_total_amount)
                 for row in daily.toLocalIterator()),
            )
            cursor.executemany(
                "INSERT INTO curated.tlc_pickup_zone VALUES (%s, %s, %s, %s, %s)",
                ((year, row.pickup_zone_id, row.trip_count, row.avg_fare_amount, row.avg_total_amount)
                 for row in zones.toLocalIterator()),
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Comma-separated Parquet paths or S3 URI glob")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument("--database-url", default=os.getenv("CURATED_DATABASE_URL"))
    parser.add_argument("--database-secret-arn")
    parser.add_argument("--db-host")
    args, _ = parser.parse_known_args()  # Glue supplies its own job arguments.
    inputs = [value.strip() for value in args.input.split(",") if value.strip()]
    if args.database_secret_arn:
        import boto3
        import psycopg

        secret = json.loads(boto3.client("secretsmanager").get_secret_value(
            SecretId=args.database_secret_arn)["SecretString"])
        args.database_url = psycopg.conninfo.make_conninfo(
            host=args.db_host, dbname="text2bi", user=secret["username"],
            password=secret["password"], connect_timeout=15)
    spark = SparkSession.builder.appName("text2bi-tlc-curation").getOrCreate()
    frame = spark.read.option("mergeSchema", "true").parquet(*inputs)
    print(json.dumps({"input_rows": frame.count(), "input_partitions": frame.rdd.getNumPartitions()}))
    if args.profile_output:
        args.profile_output.write_text(json.dumps(profile(frame), indent=2), encoding="utf-8")
    daily, zones = aggregate(frame, args.year)
    print(json.dumps({"daily_rows": daily.count(), "zone_rows": zones.count()}))
    if args.database_url:
        publish(daily, zones, args.year, args.database_url)
    spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
