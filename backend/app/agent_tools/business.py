import re

from ..schemas import (
    BusinessAnalysisSpec,
    DataAnalysisSpec,
    FormulaOperand,
    KPIDefinition,
    KPIFormulaSpec,
)
from .kpi import validate_kpi_formula


def is_time_analysis_requested(request: str) -> bool:
    lowered = request.lower()
    negative_patterns = (
        r"\b(?:do\s+not|don't|dont|no|without|exclude|omit|remove)\b.{0,60}"
        r"\b(?:growth|trends?|yoy|mom|qoq|months?|quarters?|years?|time\s+analysis)\b",
        r"(?:不要|无需|不需要|不必|删除|去掉).{0,30}"
        r"(?:增长|趋势|同比|环比|月度|季度|年度|月份|年份)",
    )
    if any(re.search(pattern, lowered) for pattern in negative_patterns):
        return False
    return any(
        token in lowered
        for token in (
            "growth",
            "trend",
            "yoy",
            "mom",
            "qoq",
            "month",
            "quarter",
            "year",
            "增长",
            "趋势",
            "同比",
            "环比",
            "月度",
            "季度",
            "年度",
        )
    )


def _aggregate_kpi(metric) -> KPIDefinition:
    formula = KPIFormulaSpec(
        kind="aggregate",
        numerator=FormulaOperand(
            table_id=metric.table_id,
            field=metric.field,
            aggregation=metric.aggregation,
        ),
    )
    return KPIDefinition(
        id=metric.id,
        name=metric.name,
        business_meaning=metric.business_meaning,
        table_id=metric.table_id,
        field=metric.field,
        aggregation=metric.aggregation,
        required_fields=metric.required_fields,
        formula=formula,
        supported=True,
    )


def _growth_kpis(data: DataAnalysisSpec, request: str) -> list[KPIDefinition]:
    results: list[KPIDefinition] = []
    preferred_time = next(
        (
            item
            for item in data.time_capabilities
            if any(
                token in item.field.lower()
                for token in ("snapshot", "report", "period", "month", "year", "time")
            )
        ),
        None,
    )
    if not preferred_time:
        return results
    available_metrics = [
        metric
        for metric in data.metrics
        if metric.table_id == preferred_time.table_id
    ]
    requested_words = set(re.findall(r"[a-z0-9]+", request.lower()))
    ranked_metrics = sorted(
        available_metrics,
        key=lambda metric: (
            metric.aggregation == "count",
            -len(
                requested_words
                & set(re.findall(r"[a-z0-9]+", f"{metric.name} {metric.field}".lower()))
            ),
        ),
    )
    base_metric = ranked_metrics[0] if ranked_metrics else None
    if not base_metric:
        return results
    comparisons = [
        ("mom", "month", "Month-over-Month Growth"),
        ("qoq", "quarter", "Quarter-over-Quarter Growth"),
        ("yoy", "year", "Year-over-Year Growth"),
    ]
    for comparison, granularity, name in comparisons:
        if comparison not in preferred_time.supported_comparisons:
            continue
        formula = KPIFormulaSpec(
            kind="period_growth",
            numerator=FormulaOperand(
                table_id=base_metric.table_id,
                field=base_metric.field,
                aggregation=base_metric.aggregation,
            ),
            time_table_id=preferred_time.table_id,
            time_field=preferred_time.field,
            time_granularity=granularity,
            comparison=comparison,
            multiplier=100.0,
        )
        results.append(
            KPIDefinition(
                id=f"{base_metric.table_id}-{comparison}-{base_metric.id}-growth",
                name=f"{name}: {base_metric.name}",
                business_meaning=(
                    f"Percentage change in {base_metric.name} versus the matching "
                    f"{comparison.upper()} period"
                ),
                table_id=base_metric.table_id,
                field=base_metric.field,
                aggregation=base_metric.aggregation,
                required_fields=[base_metric.field, preferred_time.field],
                formula=formula,
                time_granularity=granularity,
            )
        )
    return results


def build_business_fallback(request: str, data: DataAnalysisSpec) -> BusinessAnalysisSpec:
    lowered = request.lower()
    if any(token in lowered for token in ("executive", "leadership", "management", "高管", "管理层")):
        audience = "Business leadership"
    elif any(token in lowered for token in ("hr", "employee", "workforce", "员工", "人力")):
        audience = "HR leadership"
    else:
        audience = "Business users"

    requested_words = set(re.findall(r"[a-z0-9]+", lowered))
    ranked = sorted(
        data.metrics,
        key=lambda metric: len(
            requested_words & set(re.findall(r"[a-z0-9]+", metric.name.lower()))
        ),
        reverse=True,
    )
    kpis = [_aggregate_kpi(metric) for metric in ranked[:4]]
    if is_time_analysis_requested(request):
        kpis = (_growth_kpis(data, request) + kpis)[:5]

    comparisons = [
        f"Compare {field.table_id}.{field.name}"
        for field in data.dimensions[:3]
    ]
    comparisons.extend(
        f"{item.table_id}.{item.field}: {comparison.upper()}"
        for item in data.time_capabilities
        for comparison in item.supported_comparisons
        if comparison in {"mom", "qoq", "yoy"}
    )
    questions = [f"How does {kpi.name} vary across relevant segments?" for kpi in kpis[:3]]
    return BusinessAnalysisSpec(
        audience=audience,
        business_objectives=[request],
        kpis=kpis,
        comparison_requirements=comparisons,
        business_questions=questions,
        dashboard_priorities=["Validated KPIs", "Decision-relevant comparisons", "Clear exceptions"],
    )


def validate_business_analysis(
    spec: BusinessAnalysisSpec,
    data: DataAnalysisSpec,
    request: str | None = None,
) -> BusinessAnalysisSpec:
    source_request = request or (spec.business_objectives[0] if spec.business_objectives else "")
    lowered_request = source_request.lower()
    time_requested = is_time_analysis_requested(source_request)
    validated: list[KPIDefinition] = []
    for kpi in spec.kpis:
        if kpi.formula is None:
            kpi.formula = KPIFormulaSpec(
                kind="aggregate",
                numerator=FormulaOperand(
                    table_id=kpi.table_id,
                    field=kpi.field,
                    aggregation=kpi.aggregation,
                ),
            )
        errors = validate_kpi_formula(kpi, data)
        kpi.missing_fields = errors
        kpi.supported = not errors
        if not errors and (
            time_requested or not kpi.formula or kpi.formula.kind != "period_growth"
        ):
            validated.append(kpi)
        else:
            spec.additional_data_required.append(f"{kpi.name}: {'; '.join(errors)}")
    spec.kpis = validated
    if not spec.kpis:
        fallback = build_business_fallback(spec.business_objectives[0], data)
        spec.kpis = fallback.kpis

    if time_requested:
        required = {
            comparison
            for comparison, tokens in {
                "mom": ("mom", "环比"),
                "qoq": ("qoq", "季度环比"),
                "yoy": ("yoy", "同比"),
            }.items()
            if any(token in lowered_request for token in tokens)
        }
        growth_fallbacks = _growth_kpis(data, source_request)
        if not required:
            required = {item.formula.comparison for item in growth_fallbacks if item.formula}
        existing = {
            kpi.formula.comparison
            for kpi in spec.kpis
            if kpi.formula and kpi.formula.kind == "period_growth"
        }
        additions = [
            kpi
            for kpi in growth_fallbacks
            if kpi.formula
            and kpi.formula.comparison in required
            and kpi.formula.comparison not in existing
        ]
        spec.kpis = (additions + spec.kpis)[:6]
    else:
        # A stable executive dashboard should start with the strongest aggregate
        # KPIs supported by the data. LLM-proposed ratios must not displace them.
        core = [
            kpi
            for kpi in build_business_fallback(source_request, data).kpis
            if kpi.formula and kpi.formula.kind == "aggregate"
        ]
        existing = {kpi.id for kpi in core}
        spec.kpis = (core + [kpi for kpi in spec.kpis if kpi.id not in existing])[:6]
        spec.comparison_requirements = [
            item
            for item in spec.comparison_requirements
            if not any(token in item.lower() for token in ("mom", "qoq", "yoy"))
        ]

    supported_comparisons = {
        (item.table_id, item.field, comparison)
        for item in data.time_capabilities
        for comparison in item.supported_comparisons
    }
    safe_comparisons: list[str] = []
    for requirement in spec.comparison_requirements:
        lowered = requirement.lower()
        comparison = next(
            (item for item in ("mom", "qoq", "yoy") if item in lowered),
            None,
        )
        if not comparison:
            safe_comparisons.append(requirement)
            continue
        if any(
            table_id.lower() in lowered
            and field.lower() in lowered
            and comparison == supported
            for table_id, field, supported in supported_comparisons
        ):
            safe_comparisons.append(requirement)
        else:
            spec.additional_data_required.append(
                f"Unsupported comparison removed: {requirement}"
            )
    spec.comparison_requirements = safe_comparisons
    spec.dashboard_priorities = [kpi.name for kpi in spec.kpis[:5]]
    spec.additional_data_required = list(dict.fromkeys(spec.additional_data_required))
    return spec
