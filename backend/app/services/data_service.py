import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..schemas import ColumnProfile, DatasetProfile, QuerySchema, TableProfile


def table_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "table"


def read_dataframe(path: str | Path, sheet_name: str | None = None) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name or 0)
    raise ValueError("Only CSV and Excel files are supported.")


def discover_file_tables(
    path: str | Path,
    source_file: str,
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    path = Path(path)
    used = used_ids if used_ids is not None else set()
    base = table_slug(Path(source_file).stem)
    sheets: list[str | None]
    if path.suffix.lower() in {".xlsx", ".xls"}:
        sheets = list(pd.ExcelFile(path).sheet_names)
    else:
        sheets = [None]
    entries: list[dict[str, Any]] = []
    for sheet in sheets:
        proposed = table_slug(f"{base}-{sheet}") if sheet else base
        table_id = proposed
        suffix = 2
        while table_id in used:
            table_id = f"{proposed}-{suffix}"
            suffix += 1
        used.add(table_id)
        entries.append(
            {
                "id": table_id,
                "name": f"{Path(source_file).stem} / {sheet}" if sheet else Path(source_file).stem,
                "source_file": source_file,
                "path": str(path),
                "sheet_name": sheet,
            }
        )
    return entries


def write_dataset_manifest(entries: list[dict[str, Any]], path: str | Path) -> Path:
    manifest_path = Path(path)
    manifest_path.write_text(
        json.dumps({"kind": "text2bi_dataset_bundle", "version": 1, "tables": entries}),
        encoding="utf-8",
    )
    return manifest_path


def read_dataset_manifest(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() != ".json":
        return [
            {
                "id": "main",
                "name": source.stem,
                "source_file": source.name,
                "path": str(source),
                "sheet_name": None,
            }
        ]
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("kind") != "text2bi_dataset_bundle":
        raise ValueError("Unknown dataset manifest format.")
    return payload["tables"]


def read_dataset_tables(path: str | Path) -> dict[str, pd.DataFrame]:
    return {
        entry["id"]: read_dataframe(entry["path"], entry.get("sheet_name"))
        for entry in read_dataset_manifest(path)
    }


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


def _profile_table(
    df: pd.DataFrame,
    table_id: str,
    name: str,
    source_file: str,
    sheet_name: str | None,
) -> TableProfile:
    profiles: list[ColumnProfile] = []
    metrics: list[str] = []
    dimensions: list[str] = []
    dates: list[str] = []
    for column in df.columns:
        series = df[column]
        lowered = str(column).lower()
        unique_count = int(series.nunique(dropna=True))
        if lowered == "id" or lowered.endswith(" id") or lowered.endswith("_id"):
            semantic_type = "identifier"
        elif (
            pd.api.types.is_datetime64_any_dtype(series)
            or any(token in lowered for token in ("date", "time", "month"))
            or lowered == "year"
            or lowered.endswith(("_year", " year"))
        ):
            semantic_type = "date"
            dates.append(str(column))
        elif pd.api.types.is_numeric_dtype(series):
            semantic_type = "metric"
            metrics.append(str(column))
        else:
            semantic_type = "dimension"
            dimensions.append(str(column))
        profiles.append(
            ColumnProfile(
                name=str(column),
                table_id=table_id,
                dtype=str(series.dtype),
                semantic_type=semantic_type,
                null_count=int(series.isna().sum()),
                unique_count=unique_count,
                sample_values=[_clean_value(value) for value in series.dropna().head(3)],
            )
        )
    if not metrics:
        metrics = [str(column) for column in df.select_dtypes(include="number").columns][:3]
    return TableProfile(
        id=table_id,
        name=name,
        source_file=source_file,
        sheet_name=sheet_name,
        rows=len(df),
        columns=len(df.columns),
        column_profiles=profiles,
        metrics=metrics,
        dimensions=dimensions,
        dates=dates,
    )


def profile_dataset_tables(
    tables: dict[str, pd.DataFrame],
    manifest_entries: list[dict[str, Any]] | None = None,
) -> DatasetProfile:
    metadata = {entry["id"]: entry for entry in manifest_entries or []}
    table_profiles: list[TableProfile] = []
    for table_id, df in tables.items():
        entry = metadata.get(table_id, {})
        table_profiles.append(
            _profile_table(
                df,
                table_id=table_id,
                name=entry.get("name", table_id),
                source_file=entry.get("source_file", table_id),
                sheet_name=entry.get("sheet_name"),
            )
        )
    columns = [column for table in table_profiles for column in table.column_profiles]
    return DatasetProfile(
        rows=sum(table.rows for table in table_profiles),
        columns=sum(table.columns for table in table_profiles),
        column_profiles=columns,
        metrics=list(dict.fromkeys(metric for table in table_profiles for metric in table.metrics)),
        dimensions=list(
            dict.fromkeys(dimension for table in table_profiles for dimension in table.dimensions)
        ),
        dates=list(dict.fromkeys(date for table in table_profiles for date in table.dates)),
        tables=table_profiles,
    )


def profile_dataframe(df: pd.DataFrame) -> DatasetProfile:
    return profile_dataset_tables({"main": df})


def execute_query(df: pd.DataFrame, query: QuerySchema, filters: dict[str, Any] | None = None):
    working = df.copy()
    for field, selected in (filters or {}).items():
        if field not in working.columns or selected in (None, "", []):
            continue
        values = selected if isinstance(selected, list) else [selected]
        working = working[working[field].astype(str).isin([str(value) for value in values])]

    metric = query.metric
    group = query.group_by
    if query.aggregation == "count":
        if group:
            result = working.groupby(group, dropna=False).size()
        else:
            return {"value": int(len(working))}
    elif query.aggregation == "distinct_count":
        if group:
            result = working.groupby(group, dropna=False)[metric].nunique()
        else:
            return {"value": int(working[metric].nunique())}
    else:
        method = "mean" if query.aggregation == "avg" else query.aggregation
        numeric = pd.to_numeric(working[metric], errors="coerce")
        if group:
            frame = working.assign(_metric=numeric)
            result = getattr(frame.groupby(group, dropna=False)["_metric"], method)()
        else:
            value = getattr(numeric, method)()
            return {"value": 0 if pd.isna(value) else round(float(value), 2)}

    result = result.sort_values(ascending=query.sort == "asc").head(query.limit)
    return {
        "categories": [str(index) for index in result.index],
        "values": [round(float(value), 2) for value in result.values],
    }
