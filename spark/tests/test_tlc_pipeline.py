"""Small, deterministic local Spark check for the TLC curation pipeline."""

import unittest
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StructField,
    StructType,
    TimestampType,
)

from spark.tlc_pipeline import aggregate, profile


class TlcPipelineLocalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[2]")
            .appName("text2bi-tlc-local-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_profile_and_yearly_aggregates(self):
        schema = StructType([
            StructField("tpep_pickup_datetime", TimestampType()),
            StructField("PULocationID", IntegerType()),
            StructField("fare_amount", DoubleType()),
            StructField("total_amount", DoubleType()),
        ])
        rows = [
            (datetime(2024, 1, 1, 9), 10, 10.0, 12.0),
            (datetime(2024, 1, 1, 10), 10, 20.0, 24.0),
            (datetime(2024, 1, 2, 11), 20, 30.0, 36.0),
            (datetime(2024, 1, 2, 12), None, 40.0, 48.0),
            (datetime(2023, 12, 31, 23), 10, 50.0, 60.0),
        ]
        frame = self.spark.createDataFrame(rows, schema).repartition(2)

        summary = profile(frame)
        self.assertEqual(summary["rows"], 5)
        self.assertEqual(summary["partitions"], 2)
        columns = {item["name"]: item for item in summary["columns"]}
        self.assertEqual(columns["PULocationID"]["null_count"], 1)
        self.assertEqual(columns["fare_amount"]["avg"], 30.0)

        daily, zones = aggregate(frame, 2024)
        by_day = {str(row.pickup_date): row for row in daily.collect()}
        self.assertEqual(set(by_day), {"2024-01-01", "2024-01-02"})
        self.assertEqual(by_day["2024-01-01"].trip_count, 2)
        self.assertEqual(by_day["2024-01-01"].avg_fare_amount, 15.0)
        self.assertEqual(by_day["2024-01-02"].trip_count, 1)
        by_zone = {row.pickup_zone_id: row for row in zones.collect()}
        self.assertEqual(set(by_zone), {10, 20})
        self.assertEqual(by_zone[10].trip_count, 2)
        self.assertEqual(by_zone[20].avg_total_amount, 36.0)

    def test_missing_required_column_is_rejected(self):
        frame = self.spark.createDataFrame([(1,)], ["PULocationID"])
        with self.assertRaisesRegex(ValueError, "Missing TLC fields"):
            aggregate(frame, 2024)


if __name__ == "__main__":
    unittest.main()
