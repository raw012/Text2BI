# Local Spark smoke test (macOS)

This is a deterministic first step before downloading the full NYC TLC data or
deploying AWS Glue. It uses a tiny synthetic Parquet file, runs the real
`spark/tlc_pipeline.py` CLI, and checks its JSON profile and aggregate counts.
It also tests year filtering, null-zone filtering, averages, and rejection of
missing required columns.

Prerequisites: Java 17 and `uv`. From the repository root:

```sh
uv venv /private/tmp/text2bi-spark-venv --python 3.11
uv pip install --python /private/tmp/text2bi-spark-venv/bin/python -r spark/requirements.txt
export SPARK_LOCAL_HOSTNAME=localhost
export PYSPARK_PYTHON=/private/tmp/text2bi-spark-venv/bin/python
export PYSPARK_DRIVER_PYTHON=$PYSPARK_PYTHON
/private/tmp/text2bi-spark-venv/bin/python -m unittest discover -s spark/tests -v
```

All three tests should pass. The CLI test sets `local[2]` so Spark runs two
local worker threads; this demonstrates partitions and tasks, **not** a
multi-machine cluster. The separate AWS Glue job is where multiple workers
will be validated. The CLI test writes its input and output under a temporary
directory and removes them afterward; it does not need PostgreSQL or AWS.

When running the real TLC command from `spark/README.md`, keep the driver and
worker Python versions identical. A mismatch produces
`PYTHON_VERSION_MISMATCH`. The Spark UI is available at `localhost:4040` while
a long-running local job is active; inspect Jobs, Stages, Tasks, and SQL there.
