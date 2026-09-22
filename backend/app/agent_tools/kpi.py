from typing import Any

import pandas as pd

from ..schemas import (
    DataAnalysisSpec,
    FormulaOperand,
    KPIDefinition,
    KPIComputationResult,
    KPIFormulaSpec,
    KPIResultSet,
)


def _filtered_frame(df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    result = df.copy()
    for field, selected in filters.items():
        if field not in result.columns:
            raise ValueError(f"Unknown filter field: {field}")
        values = selected if isinstance(selected, list) else [selected]
        result = result[result[field].astype(str).isin([str(value) for value in values])]
    return result


def _aggregate(df: pd.DataFrame, operand: FormulaOperand) -> float | int:
    working = _filtered_frame(df, operand.filters)
    if operand.aggregation == "count":
        return int(len(working))
    if operand.field not in working.columns:
        raise ValueError(f"Unknown metric field: {operand.field}")
    if operand.aggregation == "distinct_count":
        return int(working[operand.field].nunique())
    numeric = pd.to_numeric(working[operand.field], errors="coerce")
    method = "mean" if operand.aggregation == "avg" else operand.aggregation
    value = getattr(numeric, method)()
    if pd.isna(value):
        raise ValueError("Metric has no numeric values.")
    return round(float(value), 4)


def validate_kpi_formula(
    kpi: KPIDefinition,
    data: DataAnalysisSpec,
) -> list[str]:
    fields = {(column.table_id, column.name) for column in data.semantic_columns}
    formula = kpi.formula
    errors: list[str] = []
    if formula is None:
        return ["KPI formula is missing."]
    if (
        kpi.table_id != formula.numerator.table_id
        or kpi.field != formula.numerator.field
        or kpi.aggregation != formula.numerator.aggregation
    ):
        errors.append("KPI identity must match the formula numerator.")
    operands = [formula.numerator] + ([formula.denominator] if formula.denominator else [])
    for operand in operands:
        if (operand.table_id, operand.field) not in fields:
            errors.append(f"Unknown field {operand.table_id}.{operand.field}")
        for filter_field in operand.filters:
            if (operand.table_id, filter_field) not in fields:
                errors.append(f"Unknown filter {operand.table_id}.{filter_field}")
    if formula.kind == "ratio" and formula.denominator is None:
        errors.append("Ratio formula requires a denominator.")
    if (
        formula.kind == "ratio"
        and formula.denominator
        and formula.denominator.table_id != formula.numerator.table_id
    ):
        errors.append("Cross-table ratio formulas require an explicit governed model.")
    if formula.kind == "period_growth":
        if not formula.time_field or not formula.time_table_id:
            errors.append("Period growth requires a time table and time field.")
        elif (formula.time_table_id, formula.time_field) not in fields:
            errors.append(f"Unknown time field {formula.time_table_id}.{formula.time_field}")
        if formula.comparison == "none":
            errors.append("Period growth requires MoM, QoQ, or YoY comparison.")
        if formula.time_granularity == "none":
            errors.append("Period growth requires a time granularity.")
        if formula.time_table_id != formula.numerator.table_id:
            errors.append("Period growth time field and numerator must use the same table.")
    return list(dict.fromkeys(errors))


def _period_frequency(granularity: str) -> str:
    return {
        "day": "D",
        "week": "W",
        "month": "M",
        "quarter": "Q",
        "year": "Y",
    }[granularity]


def _comparison_offset(comparison: str, granularity: str) -> int:
    if comparison == "mom" and granularity == "month":
        return 1
    if comparison == "qoq" and granularity == "quarter":
        return 1
    if comparison == "yoy":
        return {"month": 12, "quarter": 4, "year": 1}.get(granularity, 0)
    return 0


def _period_growth(
    tables: dict[str, pd.DataFrame],
    formula: KPIFormulaSpec,
) -> KPIComputationResult:
    df = _filtered_frame(tables[formula.numerator.table_id], formula.numerator.filters)
    dates = pd.to_datetime(df[formula.time_field], errors="coerce")
    valid = df.loc[dates.notna()].copy()
    valid["_period"] = dates[dates.notna()].dt.to_period(
        _period_frequency(formula.time_granularity)
    )
    if formula.numerator.aggregation == "count":
        grouped = valid.groupby("_period").size()
    elif formula.numerator.aggregation == "distinct_count":
        grouped = valid.groupby("_period")[formula.numerator.field].nunique()
    else:
        numeric = pd.to_numeric(valid[formula.numerator.field], errors="coerce")
        method = "mean" if formula.numerator.aggregation == "avg" else formula.numerator.aggregation
        grouped = getattr(valid.assign(_metric=numeric).groupby("_period")["_metric"], method)()
    grouped = grouped.dropna().sort_index()
    if grouped.empty:
        raise ValueError("No valid period values.")
    offset = _comparison_offset(formula.comparison, formula.time_granularity)
    if offset <= 0:
        raise ValueError(
            f"{formula.comparison} is incompatible with {formula.time_granularity} granularity."
        )
    current_period = grouped.index[-1]
    previous_period = current_period - offset
    if previous_period not in grouped.index:
        return KPIComputationResult(
            kpi_id="",
            status="insufficient_data",
            current_value=round(float(grouped.iloc[-1]), 4),
            series=[
                {"period": str(period), "value": round(float(value), 4)}
                for period, value in grouped.items()
            ],
            evidence={
                "current_period": str(current_period),
                "required_previous_period": str(previous_period),
            },
            message="The matching previous period is missing.",
        )
    current = float(grouped.loc[current_period])
    previous = float(grouped.loc[previous_period])
    if previous == 0:
        return KPIComputationResult(
            kpi_id="",
            status="insufficient_data",
            current_value=round(current, 4),
            previous_value=0,
            message="Previous-period value is zero; growth rate is undefined.",
        )
    change = ((current - previous) / previous) * formula.multiplier
    return KPIComputationResult(
        kpi_id="",
        status="computed",
        value=round(change, 4),
        current_value=round(current, 4),
        previous_value=round(previous, 4),
        change_rate=round(change, 4),
        series=[
            {"period": str(period), "value": round(float(value), 4)}
            for period, value in grouped.items()
        ],
        evidence={
            "current_period": str(current_period),
            "previous_period": str(previous_period),
            "formula": "(current - previous) / previous",
        },
    )


def calculate_kpi(
    kpi: KPIDefinition,
    tables: dict[str, pd.DataFrame],
    data: DataAnalysisSpec,
) -> KPIComputationResult:
    errors = validate_kpi_formula(kpi, data)
    if errors:
        return KPIComputationResult(
            kpi_id=kpi.id,
            status="unsupported",
            message="; ".join(errors),
            evidence={"validation_errors": errors},
        )
    formula = kpi.formula
    if formula is None:
        return KPIComputationResult(
            kpi_id=kpi.id,
            status="unsupported",
            message="KPI formula is missing.",
        )
    try:
        if formula.kind == "aggregate":
            value = _aggregate(tables[formula.numerator.table_id], formula.numerator)
            return KPIComputationResult(
                kpi_id=kpi.id,
                status="computed",
                value=value * formula.multiplier,
                evidence={"formula": formula.model_dump(mode="json")},
            )
        if formula.kind == "ratio":
            numerator = _aggregate(tables[formula.numerator.table_id], formula.numerator)
            denominator = _aggregate(tables[formula.denominator.table_id], formula.denominator)
            if denominator == 0:
                return KPIComputationResult(
                    kpi_id=kpi.id,
                    status="insufficient_data",
                    message="Formula denominator is zero.",
                )
            value = (float(numerator) / float(denominator)) * formula.multiplier
            return KPIComputationResult(
                kpi_id=kpi.id,
                status="computed",
                value=round(value, 4),
                evidence={
                    "numerator": numerator,
                    "denominator": denominator,
                    "formula": formula.model_dump(mode="json"),
                },
            )
        result = _period_growth(tables, formula)
        result.kpi_id = kpi.id
        return result
    except Exception as exc:
        return KPIComputationResult(
            kpi_id=kpi.id,
            status="error",
            message=str(exc),
            evidence={"formula": formula.model_dump(mode="json")},
        )


def calculate_kpis(
    business_kpis: list[KPIDefinition],
    tables: dict[str, pd.DataFrame],
    data: DataAnalysisSpec,
) -> KPIResultSet:
    return KPIResultSet(results=[calculate_kpi(kpi, tables, data) for kpi in business_kpis])
