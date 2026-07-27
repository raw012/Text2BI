from pathlib import Path
from typing import Any

import pandas as pd

from ..schemas import ColumnProfile, DatasetProfile, QuerySchema


def read_dataframe(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError("Only CSV and Excel files are supported.")


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


def profile_dataframe(df: pd.DataFrame) -> DatasetProfile:
    profiles: list[ColumnProfile] = []
    metrics: list[str] = []
    dimensions: list[str] = []
    dates: list[str] = []

    for column in df.columns:
        series = df[column]
        lowered = str(column).lower()
        unique_count = int(series.nunique(dropna=True))
        if pd.api.types.is_datetime64_any_dtype(series) or any(
            token in lowered for token in ("date", "time", "month", "year")
        ):
            semantic_type = "date"
            dates.append(str(column))
        elif pd.api.types.is_numeric_dtype(series) and unique_count > min(20, max(len(df) // 2, 5)):
            semantic_type = "metric"
            metrics.append(str(column))
        elif lowered == "id" or lowered.endswith(" id") or lowered.endswith("_id"):
            semantic_type = "identifier"
        else:
            semantic_type = "dimension"
            dimensions.append(str(column))
        profiles.append(
            ColumnProfile(
                name=str(column),
                dtype=str(series.dtype),
                semantic_type=semantic_type,
                null_count=int(series.isna().sum()),
                unique_count=unique_count,
                sample_values=[_clean_value(value) for value in series.dropna().head(3)],
            )
        )

    if not metrics:
        numeric = [str(c) for c in df.select_dtypes(include="number").columns]
        metrics = numeric[:3]
    return DatasetProfile(
        rows=len(df),
        columns=len(df.columns),
        column_profiles=profiles,
        metrics=metrics,
        dimensions=dimensions,
        dates=dates,
    )


def execute_query(df: pd.DataFrame, query: QuerySchema, filters: dict[str, Any] | None = None):
    working = df.copy()
    for field, selected in (filters or {}).items():
        if field not in working.columns or selected in (None, "", []):
            continue
        values = selected if isinstance(selected, list) else [selected]
        working = working[working[field].astype(str).isin([str(v) for v in values])]

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
