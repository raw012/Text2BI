"""End-to-end smoke test: Parquet input to CLI profile and aggregate counts."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


class TlcPipelineCliTest(unittest.TestCase):
    def test_parquet_to_profile_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "trips.parquet"
            output_path = Path(directory) / "profile.json"
            pq.write_table(pa.table({
                "tpep_pickup_datetime": [datetime(2024, 1, 1, 9), datetime(2024, 1, 2, 10)],
                "PULocationID": pa.array([10, 20], type=pa.int32()),
                "fare_amount": [10.0, 30.0],
                "total_amount": [12.0, 36.0],
            }), input_path)
            environment = os.environ.copy()
            environment.setdefault("SPARK_LOCAL_HOSTNAME", "localhost")
            environment["PYSPARK_PYTHON"] = sys.executable
            environment["PYSPARK_DRIVER_PYTHON"] = sys.executable
            environment["PYSPARK_SUBMIT_ARGS"] = "--master local[2] pyspark-shell"
            result = subprocess.run(
                [sys.executable, "spark/tlc_pipeline.py", "--input", str(input_path),
                 "--year", "2024", "--profile-output", str(output_path)],
                cwd=Path(__file__).resolve().parents[2],
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            messages = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
            self.assertEqual(messages[0]["input_rows"], 2)
            self.assertEqual(messages[1], {"daily_rows": 2, "zone_rows": 2})
            summary = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["rows"], 2)
            self.assertGreaterEqual(summary["partitions"], 1)


if __name__ == "__main__":
    unittest.main()
