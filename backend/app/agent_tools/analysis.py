import re
from typing import Any

import pandas as pd

from ..schemas import (
    DataAnalysisSpec,
    DataQualityIssue,
    DatasetProfile,
    FieldRef,
    MetricDefinition,
    SemanticColumn,
    TimeCapability,
)


def _label(name: str) -> str:
    return re.sub(r"[_\-]+", " ", name).strip().title()


def _aggregation_for(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("age", "rate", "ratio", "score", "salary", "tenure", "service")):
        return "avg"
    return "sum"


def analyze_dataset(
    tables: dict[str, pd.DataFrame],
    profile_data: dict[str, Any],
) -> DataAnalysisSpec:
    profile = DatasetProfile.model_validate(profile_data)
    semantic_columns = [
        SemanticColumn(
            name=column.name,
            table_id=column.table_id,
            semantic_type=column.semantic_type,
            business_meaning=f"{_label(column.name)} {column.semantic_type} in {column.table_id}",
            nullable=column.null_count > 0,
            unique_count=column.unique_count,
        )
        for column in profile.column_profiles
    ]

    metrics: list[MetricDefinition] = []
    dimensions: list[FieldRef] = []
    quality: list[DataQualityIssue] = []
    time_capabilities: list[TimeCapability] = []
    total_duplicates = 0
    ignored_dimensions = {"first name", "last name", "full name"}

    table_profiles = profile.tables
    if not table_profiles:
        # Backward compatibility for existing single-file Dataset records.
        table_profiles = [
            type(
                "LegacyTable",
                (),
                {
                    "id": "main",
                    "rows": profile.rows,
                    "columns": profile.columns,
                    "column_profiles": profile.column_profiles,
                    "metrics": profile.metrics,
                    "dimensions": profile.dimensions,
                    "dates": profile.dates,
                },
            )()
        ]

    for table in table_profiles:
        df = tables[table.id]
        first_field = table.column_profiles[0].name
        metrics.append(
            MetricDefinition(
                id=f"{table.id}-record-count",
                name=f"{table.id}: Record Count" if len(table_profiles) > 1 else "Record Count",
                table_id=table.id,
                business_meaning=f"Number of records in {table.id}",
                field=first_field,
                aggregation="count",
                required_fields=[first_field],
            )
        )
        for field in table.metrics:
            metrics.append(
                MetricDefinition(
                    id=f"{table.id}-{re.sub(r'[^a-z0-9]+', '-', field.lower()).strip('-')}",
                    name=f"{table.id}: {_label(field)}" if len(table_profiles) > 1 else _label(field),
                    table_id=table.id,
                    business_meaning=f"Validated {_label(field)} measure from {table.id}",
                    field=field,
                    aggregation=_aggregation_for(field),
                    required_fields=[field],
                )
            )

        cardinality = {column.name: column.unique_count for column in table.column_profiles}
        dimensions.extend(
            FieldRef(table_id=table.id, name=field)
            for field in table.dimensions
            if field.lower() not in ignored_dimensions
            and cardinality.get(field, table.rows) <= max(50, table.rows * 0.5)
        )

        for column in table.column_profiles:
            if column.null_count:
                ratio = column.null_count / max(table.rows, 1)
                quality.append(
                    DataQualityIssue(
                        code="missing_values",
                        table_id=table.id,
                        column=column.name,
                        severity="high" if ratio >= 0.3 else "medium" if ratio >= 0.1 else "low",
                        description=f"{column.null_count} missing values ({ratio:.1%})",
                        impact=f"Calculations using {table.id}.{column.name} may exclude incomplete records.",
                        recommended_action="Review missing-value handling before operational use.",
                    )
                )

        duplicate_rows = int(df.duplicated().sum())
        total_duplicates += duplicate_rows
        if duplicate_rows:
            quality.append(
                DataQualityIssue(
                    code="duplicate_rows",
                    table_id=table.id,
                    severity="medium",
                    description=f"{duplicate_rows} duplicate rows detected in {table.id}.",
                    impact="Counts and aggregations may be overstated.",
                    recommended_action="Confirm whether duplicate rows are legitimate before deduplication.",
                )
            )

        for field in table.metrics:
            numeric = pd.to_numeric(df[field], errors="coerce").dropna()
            if len(numeric) < 4:
                continue
            q1, q3 = numeric.quantile([0.25, 0.75])
            iqr = q3 - q1
            if iqr <= 0:
                continue
            outliers = int(((numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)).sum())
            if outliers:
                quality.append(
                    DataQualityIssue(
                        code="potential_outliers",
                        table_id=table.id,
                        column=field,
                        severity="low",
                        description=f"{outliers} potential IQR outliers detected.",
                        impact=f"{_label(field)} aggregations may be sensitive to extreme values.",
                        recommended_action="Compare average and distribution before drawing conclusions.",
                    )
                )

        for field in table.dates:
            parsed = pd.to_datetime(df[field], errors="coerce")
            valid = parsed.dropna()
            valid_ratio = len(valid) / max(len(df), 1)
            comparisons: list[str] = []
            if len(valid) >= 2 and valid.min() != valid.max():
                comparisons.append("trend")
                span_days = (valid.max() - valid.min()).days
                if span_days >= 60:
                    comparisons.append("mom")
                if span_days >= 180:
                    comparisons.append("qoq")
                if span_days >= 365:
                    comparisons.append("yoy")
            time_capabilities.append(
                TimeCapability(
                    field=field,
                    table_id=table.id,
                    valid_ratio=round(valid_ratio, 4),
                    min_value=valid.min().isoformat() if len(valid) else None,
                    max_value=valid.max().isoformat() if len(valid) else None,
                    supported_comparisons=comparisons,
                )
            )
            if valid_ratio < 0.8:
                quality.append(
                    DataQualityIssue(
                        code="invalid_dates",
                        table_id=table.id,
                        column=field,
                        severity="medium",
                        description=f"Only {valid_ratio:.1%} of values parse as dates.",
                        impact="Trend and period comparisons may be incomplete.",
                        recommended_action="Normalize the date field before time analysis.",
                    )
                )

    opportunities = []
    if dimensions and metrics:
        names = [f"{item.table_id}.{item.name}" for item in dimensions[:3]]
        opportunities.append(f"Compare validated metrics across {', '.join(names)}.")
    trend_fields = [
        f"{item.table_id}.{item.field}"
        for item in time_capabilities
        if "trend" in item.supported_comparisons
    ]
    if trend_fields:
        opportunities.append(f"Analyze observed period trends using {trend_fields[0]}.")
    if len(tables) > 1:
        opportunities.append(
            "Analyze each uploaded table independently; do not join tables without an explicit relationship."
        )
    if not opportunities:
        opportunities.append("Build a record-level summary using available validated fields.")

    return DataAnalysisSpec(
        dataset_summary=(
            f"{len(tables)} table(s), {profile.rows:,} total records, "
            f"and {profile.columns} total fields."
        ),
        row_count=profile.rows,
        column_count=profile.columns,
        table_ids=list(tables),
        semantic_columns=semantic_columns,
        metrics=metrics,
        dimensions=dimensions,
        time_capabilities=time_capabilities,
        quality_report=quality,
        analytical_opportunities=opportunities,
        duplicate_rows=total_duplicates,
    )


def validate_data_analysis(
    spec: DataAnalysisSpec,
    profile_data: dict[str, Any],
) -> DataAnalysisSpec:
    profile = DatasetProfile.model_validate(profile_data)
    fields = {
        (column.table_id, column.name)
        for column in profile.column_profiles
    }
    spec.metrics = [
        metric
        for metric in spec.metrics
        if (metric.table_id, metric.field) in fields
        and all((metric.table_id, field) in fields for field in metric.required_fields)
    ]
    spec.dimensions = [
        field for field in spec.dimensions if (field.table_id, field.name) in fields
    ]
    spec.time_capabilities = [
        item
        for item in spec.time_capabilities
        if (item.table_id, item.field) in fields
    ]
    spec.table_ids = [table_id for table_id in spec.table_ids if table_id in {key[0] for key in fields}]
    return spec
