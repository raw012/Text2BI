"""Governed, live PostgreSQL questions with Secrets Manager credentials."""

import re
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlglot import exp, parse

from ..config import settings
from ..schemas import SqlPlan
from .llm_service import qwen_structured


TABLE_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*\.[a-zA-Z_][a-zA-Z_0-9]*$")
ALLOWED_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "DATE_TRUNC", "EXTRACT",
                     "ROUND", "COALESCE", "NULLIF", "ABS", "LOWER", "UPPER", "TO_CHAR"}
ROW_LIMIT = 100


@lru_cache(maxsize=1)
def _secrets():
    import boto3

    return boto3.client("secretsmanager")


def validate_url(database_url: str) -> None:
    parsed = make_url(database_url)
    if parsed.drivername != "postgresql+psycopg" or not parsed.password:
        raise ValueError("A postgresql+psycopg URL with a password is required.")
    if settings.db_host and parsed.host != settings.db_host:
        raise ValueError("Live connections must use the configured PostgreSQL host.")


def validate_tables(tables: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(tables))
    if not normalized or len(normalized) > 12 or any(not TABLE_NAME.fullmatch(t) for t in normalized):
        raise ValueError("Provide 1–12 schema-qualified table names.")
    return normalized


def source_schema(database_url: str, tables: list[str], *, require_readonly: bool = False) -> list[dict]:
    source = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    try:
        inspector = inspect(source)
        result = []
        with source.connect() as connection:
            if require_readonly:
                role = connection.execute(text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
                )).one()
                if any(role):
                    raise ValueError("Use a non-admin read-only database role.")
            for qualified in tables:
                schema, name = qualified.split(".", 1)
                if name not in inspector.get_table_names(schema=schema):
                    raise ValueError(f"Table {qualified} was not found.")
                if require_readonly:
                    if not connection.execute(text(
                        "SELECT has_table_privilege(current_user, :table, 'SELECT')"
                    ), {"table": qualified}).scalar_one():
                        raise ValueError(f"The role cannot read {qualified}.")
                    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        if connection.execute(text(
                            "SELECT has_table_privilege(current_user, :table, :privilege)"
                        ), {"table": qualified, "privilege": privilege}).scalar_one():
                            raise ValueError("Use a role without write access to the allowed tables.")
                result.append({
                    "table": qualified,
                    "columns": [{"name": item["name"], "type": str(item["type"])}
                                for item in inspector.get_columns(name, schema=schema)],
                })
        return result
    finally:
        source.dispose()


def save_secret(database_url: str) -> str:
    if not settings.live_connection_secret_prefix:
        raise RuntimeError("Live connection secret storage is not configured.")
    name = f"{settings.live_connection_secret_prefix.rstrip('/')}/{uuid4().hex}"
    return _secrets().create_secret(Name=name, SecretString=database_url)["ARN"]


def load_secret(arn: str) -> str:
    return _secrets().get_secret_value(SecretId=arn)["SecretString"]


def delete_secret(arn: str) -> None:
    _secrets().delete_secret(SecretId=arn, RecoveryWindowInDays=7)


def validate_sql(sql: str, allowed_tables: list[str]) -> str:
    try:
        statements = parse(sql, read="postgres")
    except Exception as exc:
        raise ValueError("The generated SQL could not be parsed.") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("Only one SELECT statement is permitted.")
    statement = statements[0]
    forbidden = (exp.With, exp.Into, exp.Insert, exp.Update, exp.Delete, exp.Drop,
                 exp.Create, exp.Alter, exp.Command, exp.Merge)
    if any(isinstance(node, forbidden) for node in statement.walk()):
        raise ValueError("The query contains a forbidden operation.")
    referenced = {f"{table.db}.{table.name}" for table in statement.find_all(exp.Table)}
    if not referenced or not referenced.issubset(set(allowed_tables)):
        raise ValueError("The query references a table outside the allowlist.")
    for function in statement.find_all(exp.Anonymous):
        if function.name.upper() not in ALLOWED_FUNCTIONS:
            raise ValueError("The query uses an unapproved SQL function.")
    return statement.sql(dialect="postgres")


def _safe_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def ask_live(secret_arn: str, tables: list[str], question: str) -> dict:
    database_url = load_secret(secret_arn)
    schema = source_schema(database_url, tables)
    plan = qwen_structured(
        "data_analysis",
        "Write one PostgreSQL SELECT query answering the question. Use only the supplied "
        "schema-qualified tables and columns. No CTE, DML, DDL, comments, system tables, "
        "or unsafe functions. Return SQL only in the sql field.",
        {"question": question, "live_schema": schema, "max_rows": ROW_LIMIT},
        SqlPlan,
    )
    if plan is None:
        raise ValueError("The SQL planner is unavailable or could not produce a valid plan.")
    sql = validate_sql(plan.sql, tables)
    source = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    try:
        with source.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
            result = connection.execute(text(f"SELECT * FROM ({sql}) AS governed_result LIMIT :row_limit"),
                                        {"row_limit": ROW_LIMIT})
            rows = [{key: _safe_value(value) for key, value in row._mapping.items()}
                    for row in result]
    finally:
        source.dispose()
    if not rows:
        answer = "The query returned no rows."
    elif len(rows) == 1 and len(rows[0]) == 1:
        answer = f"The result is {next(iter(rows[0].values()))}."
    else:
        first = ", ".join(f"{key}: {value}" for key, value in rows[0].items())
        answer = f"The query returned {len(rows)} row(s). First row: {first}."
    return {"answer": answer, "sql": sql, "row_count": len(rows), "rows": rows,
            "schema": schema}
