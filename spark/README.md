# NYC TLC Spark pipeline

Use the [NYC TLC official Parquet downloads](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
The January 2024 yellow-taxi file is a useful first local input. Install Java
17 and Python 3.11, then install `spark/requirements.txt` in a virtual
environment. Run from the repository root:

```powershell
python spark/tlc_pipeline.py --input data/yellow_tripdata_2024-01.parquet --year 2024 --profile-output data/profile-2024-01.json
```

The job prints input row and partition counts, daily aggregate row count, and
pickup-zone aggregate row count. Open the local Spark UI at `localhost:4040`
while it runs and confirm more than one task. Compare null counts and numeric
min/max/mean from `profile-2024-01.json` with Pandas on the same small sample.
For a single month, `curated.tlc_daily` should have one row per pickup date in
that month, after excluding dates outside the requested year and records with
null pickup zone.

To publish to local PostgreSQL, set `CURATED_DATABASE_URL` to a Postgres
connection string in your shell before running the job. The job creates
`curated.tlc_daily` and `curated.tlc_pickup_zone` and replaces only the
requested year in one transaction. Running it twice will not duplicate rows.
Call `POST /datasets/connect_curated_tlc?table=tlc_daily` on an app instance
using the same PostgreSQL database. It registers the small serving table using
server-side credentials. Select the resulting source in the dashboard workflow;
the app loads a few hundred curated rows instead of raw trip records. Reconnect
after each pipeline run until the live connector in phase 3 is configured.

For AWS Glue, copy all twelve monthly files for one year to a private S3
prefix, then upload `tlc_pipeline.py` to the same bucket as
`spark/tlc_pipeline.py`. Deploy `infra/spark.yml` with that bucket, an S3
glob for the raw files, the RDS host and secret ARN from the foundation stack,
and a VPC subnet. Glue workers need S3 and Secrets Manager connectivity from
the subnet (NAT or appropriate VPC endpoints). The two-worker job uses the
same Spark code and writes the same serving tables. Run it manually twice and
check CloudWatch partition counts and idempotent row counts. Schedule it only
after the manual run has been validated. Spot-check a known day against an
Athena count over the raw Parquet.

The Glue script reads the RDS-managed password from Secrets Manager at run
time. Its role needs S3 read and secret read; RDS ingress is limited to the
Glue worker security group. AWS creation, Glue execution, and Athena comparison
remain pending a limited non-root profile.
