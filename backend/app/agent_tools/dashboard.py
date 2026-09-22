import base64
import html
import json
import mimetypes
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from ..schemas import (
    BusinessAnalysisSpec,
    ComponentSchema,
    DashboardSchema,
    DataAnalysisSpec,
    EvaluationIssue,
    EvaluationResult,
    FilterSchema,
    InsightSchema,
    KPIResultSet,
    LayoutSchema,
    QuerySchema,
    RenderArtifact,
)
from ..services.data_service import execute_query
from ..config import settings
from .business import is_time_analysis_requested


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _title_from_request(request: str) -> str:
    title = request.strip().splitlines()[0].split(".")[0]
    return title[:72] or "Business Performance Overview"


def _theme(
    preferences: str | None,
    brand_identity: dict[str, Any] | None = None,
) -> dict[str, str]:
    text = (preferences or "").lower()
    if "dark" in text or "深色" in text:
        return {
            "primary": "#60A5FA",
            "accent": "#2DD4BF",
            "background": "#07111F",
            "surface": "#101C2E",
            "text": "#E2E8F0",
            "font_family": "Inter",
        }
    if "mercedes" in text or "奔驰" in text:
        return {
            "primary": "#00ADEF",
            "accent": "#111827",
            "background": "#F4F6F8",
            "surface": "#FFFFFF",
            "text": "#111827",
            "font_family": "Inter",
        }
    theme = {
        "primary": "#2563EB",
        "accent": "#14B8A6",
        "background": "#F4F7FB",
        "surface": "#FFFFFF",
        "text": "#0F172A",
        "font_family": "Inter",
    }
    if brand_identity:
        theme["primary"] = brand_identity.get("primary_color", theme["primary"])
        theme["accent"] = brand_identity.get("accent_color", theme["accent"])
    return theme


def _kpi_layout(index: int, count: int) -> LayoutSchema:
    widths = {
        1: [12],
        2: [6, 6],
        3: [4, 4, 4],
        4: [3, 3, 3, 3],
        5: [3, 3, 2, 2, 2],
    }.get(count, [2, 2, 2, 2, 2, 2])
    return LayoutSchema(x=sum(widths[:index]), y=0, w=widths[index], h=2)


def build_dashboard_fallback(
    dataset_id: int,
    request: str,
    data: DataAnalysisSpec,
    business: BusinessAnalysisSpec,
    kpi_results: KPIResultSet,
    logo_url: str | None,
    preferences: str | None,
    brand_identity: dict[str, Any] | None = None,
    logo_source: str | None = None,
    revision: int = 1,
) -> DashboardSchema:
    components: list[ComponentSchema] = []
    time_requested = is_time_analysis_requested(request)
    computed = {result.kpi_id: result for result in kpi_results.results}
    selected_kpis = [
        kpi
        for kpi in business.kpis
        if (
            (time_requested or not kpi.formula or kpi.formula.kind != "period_growth")
            and computed.get(kpi.id)
            and computed[kpi.id].status == "computed"
        )
    ][:5]
    for index, kpi in enumerate(selected_kpis):
        lowered_name = kpi.name.lower()
        unit = (
            "%"
            if (
                kpi.formula
                and kpi.formula.kind in {"ratio", "period_growth"}
                and kpi.formula.multiplier == 100
            )
            or any(token in lowered_name for token in ("rate", "ratio", "percent", "率", "占比"))
            else "years"
            if any(token in lowered_name for token in ("age", "tenure", "service year", "年龄", "工龄"))
            else None
        )
        components.append(
            ComponentSchema(
                id=f"kpi-{_slug(kpi.id or kpi.name)}",
                type="kpi",
                title=kpi.name,
                subtitle=kpi.business_meaning,
                metric_id=kpi.id,
                query=QuerySchema(
                    table_id=kpi.table_id,
                    metric=kpi.field,
                    aggregation=kpi.aggregation,
                ),
                formula=kpi.formula,
                computed_value=computed[kpi.id].value,
                computation_status=computed[kpi.id].status,
                computation_message=computed[kpi.id].message,
                computation_evidence=(
                    computed[kpi.id].evidence if kpi.id in computed else {}
                ),
                layout=_kpi_layout(index, len(selected_kpis)),
                style={"unit": unit} if unit else {},
            )
        )

    metric = next(
        (kpi for kpi in selected_kpis if kpi.aggregation == "count"),
        selected_kpis[0] if selected_kpis else None,
    )
    chart_y = 2
    semantic_map = {
        (column.table_id, column.name): column for column in data.semantic_columns
    }
    comparison_dimensions = [
        dimension
        for dimension in data.dimensions
        if 1
        < semantic_map[(dimension.table_id, dimension.name)].unique_count
        <= 25
    ][:5]
    for index, dimension in enumerate(comparison_dimensions):
        chart_metric = next(
            (
                kpi
                for kpi in selected_kpis
                if kpi.table_id == dimension.table_id and kpi.aggregation == "count"
            ),
            next(
                (kpi for kpi in selected_kpis if kpi.table_id == dimension.table_id),
                None,
            ),
        )
        if not chart_metric:
            break
        width = 4 if index < 3 else 6
        x = (index % 3) * 4 if index < 3 else (index - 3) * 6
        y = chart_y if index < 3 else chart_y + 5
        is_gender = any(token in dimension.name.lower() for token in ("gender", "sex", "性别"))
        components.append(
            ComponentSchema(
                id=f"comparison-{_slug(dimension.table_id)}-{_slug(dimension.name)}",
                type="pie" if is_gender else "bar",
                title=f"{chart_metric.name} by {dimension.name}",
                subtitle=f"Validated comparison in {dimension.table_id}",
                metric_id=chart_metric.id,
                formula=chart_metric.formula,
                query=QuerySchema(
                    table_id=dimension.table_id,
                    group_by=dimension.name,
                    metric=chart_metric.field,
                    aggregation=chart_metric.aggregation,
                    limit=8,
                ),
                layout=LayoutSchema(x=x, y=y, w=width, h=5),
            )
        )

    trend_capability = next(
        (
            item
            for item in data.time_capabilities
            if "trend" in item.supported_comparisons
            and item.table_id == metric.table_id
            and any(
                token in item.field.lower()
                for token in ("snapshot", "report", "period", "month", "year", "time")
            )
        ),
        None,
    )
    if time_requested and trend_capability and metric:
        components.append(
            ComponentSchema(
                id=f"trend-{_slug(trend_capability.field)}",
                type="line",
                title=f"{metric.name} trend",
                subtitle=f"Observed values over {trend_capability.field}",
                metric_id=metric.id,
                formula=metric.formula,
                query=QuerySchema(
                    table_id=trend_capability.table_id,
                    group_by=trend_capability.field,
                    metric=metric.field,
                    aggregation=metric.aggregation,
                    sort="asc",
                    limit=24,
                ),
                layout=LayoutSchema(
                    x=0,
                    y=chart_y + (10 if len(comparison_dimensions) > 3 else 5),
                    w=12,
                    h=5,
                ),
            )
        )

    if not components:
        first = data.semantic_columns[0]
        components.append(
            ComponentSchema(
                id="kpi-record-count",
                type="kpi",
                title="Record Count",
                metric_id="record-count",
                query=QuerySchema(
                    table_id=first.table_id,
                    metric=first.name,
                    aggregation="count",
                ),
                layout=LayoutSchema(x=0, y=0, w=12, h=2),
            )
        )

    filter_fields = [
        field
        for field in data.dimensions
        if 1 < semantic_map[(field.table_id, field.name)].unique_count <= 30
    ][:3]
    filters = [
        FilterSchema(
            id=f"filter-{_slug(field.table_id)}-{_slug(field.name)}",
            table_id=field.table_id,
            field=field.name,
            label=field.name,
            type="select",
        )
        for field in filter_fields
    ]
    return DashboardSchema(
        revision=revision,
        title=_title_from_request(request),
        description=f"Designed for {business.audience}: {business.business_objectives[0]}",
        dataset_id=dataset_id,
        company_name=(brand_identity or {}).get("company_name"),
        logo_url=logo_url,
        logo_source=logo_source,
        theme=_theme(preferences, brand_identity),
        filters=filters,
        components=components,
    )


def normalize_layout(dashboard: DashboardSchema) -> DashboardSchema:
    result = dashboard.model_copy(deep=True)
    kpis = [component for component in result.components if component.type == "kpi"]
    charts = [component for component in result.components if component.type != "kpi"]
    if kpis:
        for index, component in enumerate(kpis):
            component.layout = _kpi_layout(index, len(kpis))
    y = 2 if kpis else 0
    column = 0
    for component in charts:
        if component.type in {"line", "area", "table"}:
            if column:
                y += 5
                column = 0
            component.layout = LayoutSchema(x=0, y=y, w=12, h=5)
            y += 5
        else:
            component.layout = LayoutSchema(x=column * 4, y=y, w=4, h=5)
            column += 1
            if column == 3:
                y += 5
                column = 0
    return result


def apply_user_instruction(
    dashboard: DashboardSchema,
    instruction: str,
    data: DataAnalysisSpec,
) -> DashboardSchema:
    result = dashboard.model_copy(deep=True)
    result.revision += 1
    lowered = instruction.lower()
    if "dark" in lowered or "深色" in lowered:
        result.theme = _theme("dark")
    if "mercedes" in lowered or "奔驰" in lowered:
        result.theme = _theme("mercedes")
    if "purple" in lowered or "紫色" in lowered:
        result.theme.update({"primary": "#7C3AED", "accent": "#EC4899"})
    if "executive" in lowered or "高管" in lowered:
        result.components = [
            component
            for component in result.components
            if component.type == "kpi" or component.type in {"bar", "line"}
        ][:6]
    if "bar" in lowered or "柱状" in lowered:
        for component in result.components:
            if component.type in {"line", "area", "pie"}:
                component.type = "bar"
    if "line" in lowered or "折线" in lowered:
        for component in result.components:
            if component.type == "bar" and component.query.group_by in {
                item.field for item in data.time_capabilities
            }:
                component.type = "line"
    if "compact" in lowered or "紧凑" in lowered:
        for component in result.components:
            component.layout.h = max(2, component.layout.h - 1)
    requested_aggregation = None
    if "average" in lowered or " avg" in f" {lowered}" or "平均" in lowered:
        requested_aggregation = "avg"
    elif "sum" in lowered or "total" in lowered or "总和" in lowered or "求和" in lowered:
        requested_aggregation = "sum"
    if requested_aggregation:
        numeric_fields = {
            (metric.table_id, metric.field)
            for metric in data.metrics
            if metric.aggregation != "count"
        }
        words = {
            word
            for word in re.findall(r"[a-z0-9]+", lowered)
            if len(word) > 2
            and word not in {"change", "make", "into", "average", "total", "sum"}
        }
        candidates = [
            component
            for component in result.components
            if (component.query.table_id, component.query.metric) in numeric_fields
        ]
        targeted = [
            component
            for component in candidates
            if words & set(re.findall(r"[a-z0-9]+", component.title.lower()))
        ]
        for component in targeted or candidates[:1]:
            component.query.aggregation = requested_aggregation
    result.description = f"{result.description} · Latest request: {instruction[:160]}"
    return normalize_layout(result)


def _derive_insights(
    dashboard: DashboardSchema,
    component_data: dict[str, dict[str, Any]],
) -> list[InsightSchema]:
    insights: list[InsightSchema] = []
    for component in dashboard.components:
        result = component_data.get(component.id, {})
        if "value" in result:
            value = result["value"]
            insights.append(
                InsightSchema(
                    text=f"{component.title}: {value:,}" if isinstance(value, int) else f"{component.title}: {value}",
                    component_id=component.id,
                    evidence={"query": component.query.model_dump(), "value": value},
                )
            )
        elif result.get("categories") and result.get("values"):
            values = result["values"]
            index = max(range(len(values)), key=values.__getitem__)
            category = result["categories"][index]
            value = values[index]
            insights.append(
                InsightSchema(
                    text=f"{category} has the highest displayed value in {component.title}: {value}.",
                    component_id=component.id,
                    evidence={
                        "query": component.query.model_dump(),
                        "category": category,
                        "value": value,
                    },
                )
            )
        if len(insights) >= 4:
            break
    return insights


def _portable_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


def _offline_table_payload(
    dashboard: DashboardSchema,
    tables: dict[str, pd.DataFrame],
) -> dict[str, list[dict[str, Any]]]:
    fields: dict[str, set[str]] = {}

    def include(table_id: str, field: str | None) -> None:
        if field:
            fields.setdefault(table_id, set()).add(field)

    for filter_spec in dashboard.filters:
        include(filter_spec.table_id, filter_spec.field)
    for component in dashboard.components:
        include(component.query.table_id, component.query.metric)
        include(component.query.table_id, component.query.group_by)
        if not component.formula:
            continue
        operands = [component.formula.numerator]
        if component.formula.denominator:
            operands.append(component.formula.denominator)
        for operand in operands:
            include(operand.table_id, operand.field)
            for filter_field in operand.filters:
                include(operand.table_id, filter_field)
        include(component.formula.time_table_id or "", component.formula.time_field)

    payload: dict[str, list[dict[str, Any]]] = {}
    for table_id, selected_fields in fields.items():
        frame = tables.get(table_id)
        if frame is None:
            continue
        columns = [field for field in sorted(selected_fields) if field in frame.columns]
        payload[table_id] = [
            {column: _portable_value(value) for column, value in row.items()}
            for row in frame[columns].to_dict(orient="records")
        ]
    return payload


def _embedded_logo(logo_url: str | None) -> str | None:
    if not logo_url or logo_url.startswith("data:"):
        return logo_url
    parsed = urlparse(logo_url)
    if "/uploads/" not in parsed.path:
        return logo_url
    candidate = settings.upload_dir / Path(parsed.path).name
    if not candidate.is_file():
        return logo_url
    mime = mimetypes.guess_type(candidate.name)[0] or "image/png"
    encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _offline_document(
    dashboard: DashboardSchema,
    component_data: dict[str, dict[str, Any]],
    tables: dict[str, pd.DataFrame],
    template_id: str = "generic-executive",
) -> str:
    payload = json.dumps(
        {
            "dashboard": dashboard.model_dump(mode="json"),
            "data": component_data,
            "tables": _offline_table_payload(dashboard, tables),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    logo_url = _embedded_logo(dashboard.logo_url)
    logo = (
        f'<img class="company-logo" src="{html.escape(logo_url)}" alt="Company logo">'
        if logo_url
        else ""
    )
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>__TITLE__</title>
  <style>
    *{box-sizing:border-box}
    :root{--brand-primary:__PRIMARY__;--brand-accent:__ACCENT__;--surface:__SURFACE__;--text:__TEXT__}
    body{margin:0;background:#f1f3f4;color:var(--text);font-family:Inter,"Helvetica Neue",Arial,sans-serif}
    .app-header{height:63px;padding:0 32px;display:flex;align-items:center;justify-content:space-between;background:#fff;border-bottom:1px solid #dfe4e7}
    .app-brand{display:flex;align-items:center;gap:11px}.app-brand strong{display:block;font-size:17px}.app-brand span{display:block;margin-top:2px;color:#85909a;font-size:8px;letter-spacing:.18em;text-transform:uppercase}
    .offline-badge,.run-status{padding:7px 10px;border:1px solid #dce2e6;background:#fff;font-size:10px}.run-status{color:#14764d;background:#e8f7ef;border-color:#d6eee1}
    .report-page{max-width:1520px;margin:auto;background:#f4f5f6;min-height:calc(100vh - 63px)}
    .report-titlebar{min-height:122px;padding:25px 32px;display:flex;align-items:center;justify-content:space-between;background:#fff;border-bottom:1px solid #d6dcdf}
    .company-lockup{min-width:0;display:flex;align-items:center;gap:16px}.company-logo{width:58px;height:58px;object-fit:contain}
    .company-name{margin:0 0 5px;color:var(--brand-accent);font-size:9px;font-weight:800;letter-spacing:.15em;text-transform:uppercase}
    h1{max-width:980px;margin:0;overflow:hidden;font-size:34px;font-weight:550;letter-spacing:-.04em;line-height:1.1;text-overflow:ellipsis;white-space:nowrap}
    .description{max-width:920px;margin:7px 0 0;overflow:hidden;color:#727a80;font-size:10px;text-overflow:ellipsis;white-space:nowrap}
    .evaluation{min-width:170px;padding-left:22px;display:grid;grid-template-columns:1fr auto;border-left:1px solid #e2e6e8}.evaluation span{grid-column:1/-1;width:max-content;padding:4px 7px;color:#14764d;background:#e8f7ef;font-size:8px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.evaluation b{margin-top:8px;font-size:24px;font-weight:500}.evaluation small{align-self:end;margin-bottom:5px;color:#8b9297;font-size:8px;text-transform:uppercase}
    .filter-strip{min-height:64px;padding:11px 32px;display:flex;align-items:end;gap:10px;border-bottom:1px solid #cfd5d9;background:#e9edef}.filter-strip>strong{align-self:center;margin-right:6px;color:#596168;font-size:9px;letter-spacing:.12em;text-transform:uppercase}.filter-strip label{min-width:150px}.filter-strip label span{display:block;margin-bottom:4px;color:#747c82;font-size:8px;font-weight:700;text-transform:uppercase}.filter-strip select,.filter-strip button{height:34px;border:1px solid #c9d0d4;border-radius:0;background:#fff;color:#333a40;font-size:10px}.filter-strip select{width:100%;padding:0 28px 0 9px}.filter-strip button{margin-left:auto;padding:0 14px}
    .dashboard-section{padding:22px 32px 26px}.section-intro{margin-bottom:16px;display:flex;align-items:end;justify-content:space-between}.eyebrow{margin:0 0 5px;color:#087faa;font-size:8px;font-weight:800;letter-spacing:.18em}.section-intro h2{margin:0;font-size:25px;font-weight:400;letter-spacing:-.035em}.section-intro>span{color:#7f878c;font-size:9px}
    .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:11px;margin-bottom:11px}.kpi-card{position:relative;min-height:126px;padding:18px;overflow:hidden;border:1px solid #dce1e5;border-top:3px solid var(--brand-primary);background:#fff}.kpi-card:nth-child(2n){border-top-color:var(--brand-accent)}.kpi-title{margin:0;color:#6a737a;font-size:9px;font-weight:800;letter-spacing:.1em;text-transform:uppercase}.kpi-card strong{display:block;margin-top:13px;font-size:32px;font-weight:500;letter-spacing:-.035em}.kpi-card small{display:block;margin-top:7px;color:#858d93;font-size:8px;line-height:1.35}
    .report-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:11px}.chart-panel{min-width:0;min-height:300px;padding:16px 17px 8px;border:1px solid #dce1e5;background:#fff}.chart-panel header{min-height:43px;border-bottom:1px solid #edf0f2}.chart-panel header p{margin:0 0 4px;color:#087faa;font-size:7px;font-weight:800;letter-spacing:.15em}.chart-panel h3{margin:0;font-size:13px}.chart{display:block;width:100%;height:235px}
    .result-footer{padding:0 32px 30px}.insight-panel{padding:20px;border:1px solid #dce1e5;background:#fff}.insight-list{display:grid;grid-template-columns:1fr 1fr;gap:8px 20px}.insight-list p{margin:0;color:#4e575e;font-size:10px;line-height:1.5}.insight-list p::before{content:"";display:inline-block;width:6px;height:6px;margin-right:8px;border-radius:50%;background:var(--brand-accent)}
    @media(max-width:900px){.app-header,.report-titlebar,.dashboard-section,.result-footer{padding-left:18px;padding-right:18px}.report-titlebar{align-items:flex-start;gap:18px;flex-direction:column}.evaluation{border-left:0;padding-left:0}.filter-strip{align-items:stretch;flex-direction:column;padding:14px 18px}.filter-strip button{margin-left:0}.chart-panel{grid-column:span 12!important}.insight-list{grid-template-columns:1fr}}
  </style>
</head>
<body class="template-__TEMPLATE_CLASS__">
  <header class="app-header"><div class="app-brand"><div><strong>Text2BI</strong><span>AI analytics studio</span></div></div><div><span class="run-status">Passed</span> <span class="offline-badge">Offline interactive report</span></div></header>
  <main class="report-page">
    <header class="report-titlebar"><div class="company-lockup">__LOGO__<div><p class="company-name">__COMPANY__</p><h1>__TITLE__</h1><p class="description">__DESCRIPTION__</p></div></div><div class="evaluation"><span>✓ __STATUS__</span><b>__SCORE__/100</b><small>BI evaluation</small></div></header>
    <section id="filters" class="filter-strip"><strong>Filter report</strong><button id="reset" type="button">Reset</button></section>
    <section class="dashboard-section"><div class="section-intro"><div><p class="eyebrow">EXECUTIVE OVERVIEW</p><h2>Key performance at a glance</h2></div><span>Calculated from embedded source fields</span></div><div id="kpis" class="kpi-grid"></div><div id="charts" class="report-grid"></div></section>
    <section class="result-footer"><div class="insight-panel"><p class="eyebrow">EVIDENCE-BACKED INSIGHTS</p><div id="insights" class="insight-list"></div></div></section>
  </main>
  <script id="report-data" type="application/json">__PAYLOAD__</script>
  <script>
    const payload=JSON.parse(document.getElementById("report-data").textContent);
    const activeFilters={};
    const charts=new Map();
    const palette=[payload.dashboard.theme.accent,payload.dashboard.theme.primary,"#7C8791","#B8C0C7","#9ACCE0","#486575"];
    const byId=(id)=>document.getElementById(id);
    const clean=(value)=>value===null||value===undefined?"":String(value);
    const same=(left,right)=>clean(left)===clean(right);
    const formatNumber=(value,unit)=>{
      if(value===null||value===undefined||!Number.isFinite(Number(value)))return "—";
      const n=Number(value);const text=Math.abs(n)>=1000?Intl.NumberFormat("en",{notation:"compact",maximumFractionDigits:1}).format(n):Intl.NumberFormat("en",{maximumFractionDigits:1}).format(n);
      return unit==="%"?text+"%":unit==="years"?text+" yrs":text;
    };
    function filteredRows(tableId,fixed={}){
      return (payload.tables[tableId]||[]).filter(row=>{
        const userMatch=(payload.dashboard.filters||[]).filter(f=>f.table_id===tableId).every(f=>!activeFilters[f.id]||same(row[f.field],activeFilters[f.id]));
        const fixedMatch=Object.entries(fixed||{}).every(([field,value])=>Array.isArray(value)?value.some(item=>same(row[field],item)):same(row[field],value));
        return userMatch&&fixedMatch;
      });
    }
    function aggregate(rows,field,method){
      if(method==="count")return rows.length;
      if(method==="distinct_count")return new Set(rows.map(row=>clean(row[field])).filter(Boolean)).size;
      const values=rows.map(row=>Number(row[field])).filter(Number.isFinite);
      if(!values.length)return null;
      if(method==="sum")return values.reduce((a,b)=>a+b,0);
      if(method==="min")return Math.min(...values);
      if(method==="max")return Math.max(...values);
      return values.reduce((a,b)=>a+b,0)/values.length;
    }
    function queryComponent(component){
      const fixed=component.formula?.numerator?.filters||{};
      const rows=filteredRows(component.query.table_id,fixed);
      if(!component.query.group_by)return {value:aggregate(rows,component.query.metric,component.query.aggregation)};
      const groups=new Map();
      for(const row of rows){const key=clean(row[component.query.group_by])||"Unknown";if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row)}
      let entries=[...groups].map(([name,items])=>[name,aggregate(items,component.query.metric,component.query.aggregation)]).filter(([,value])=>value!==null);
      entries.sort((a,b)=>component.query.sort==="asc"?a[1]-b[1]:b[1]-a[1]);entries=entries.slice(0,component.query.limit);
      return {categories:entries.map(item=>item[0]),values:entries.map(item=>item[1])};
    }
    function renderFilters(){
      const root=byId("filters");const reset=byId("reset");
      for(const f of payload.dashboard.filters||[]){
        const label=document.createElement("label");const name=document.createElement("span");name.textContent=f.label;label.appendChild(name);
        const select=document.createElement("select");select.setAttribute("aria-label",f.label);const all=document.createElement("option");all.value="";all.textContent="All";select.appendChild(all);
        const options=[...new Set((payload.tables[f.table_id]||[]).map(row=>clean(row[f.field])).filter(Boolean))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
        for(const option of options){const item=document.createElement("option");item.value=option;item.textContent=option;select.appendChild(item)}
        select.addEventListener("change",()=>{activeFilters[f.id]=select.value;renderCharts();renderInsights()});label.appendChild(select);root.insertBefore(label,reset);
      }
      reset.addEventListener("click",()=>{for(const key of Object.keys(activeFilters))delete activeFilters[key];root.querySelectorAll("select").forEach(select=>select.value="");renderCharts();renderInsights()});
    }
    function renderKpis(){
      const root=byId("kpis");root.replaceChildren();
      for(const component of payload.dashboard.components.filter(c=>c.type==="kpi")){
        const card=document.createElement("article");card.className="kpi-card";const title=document.createElement("p");title.className="kpi-title";title.textContent=component.title;
        const value=document.createElement("strong");value.textContent=component.computation_status&&component.computation_status!=="computed"?"—":formatNumber(component.computed_value,component.style?.unit);
        const note=document.createElement("small");note.textContent=value.textContent==="—"?(component.computation_message||"Insufficient source data for this KPI"):(component.subtitle||"Calculated from validated source data");
        card.append(title,value,note);root.appendChild(card);
      }
    }
    function canvasContext(canvas){
      const box=canvas.getBoundingClientRect();const ratio=Math.max(1,window.devicePixelRatio||1);canvas.width=Math.round(box.width*ratio);canvas.height=Math.round(box.height*ratio);const ctx=canvas.getContext("2d");ctx.setTransform(ratio,0,0,ratio,0,0);return {ctx,width:box.width,height:box.height};
    }
    function drawChart(canvas,type,data){
      const {ctx,width,height}=canvasContext(canvas);ctx.clearRect(0,0,width,height);ctx.font="10px Inter,Arial";ctx.fillStyle="#687079";ctx.strokeStyle="#E7ECEF";const categories=data.categories||[],values=data.values||[];
      if(!values.length){ctx.fillText("No data for the selected filters",18,40);return}
      if(type==="pie"){
        const total=values.reduce((a,b)=>a+b,0)||1,cx=width/2,cy=height/2-8,r=Math.min(width,height)*.3,inner=r*.58;let start=-Math.PI/2;
        values.forEach((value,index)=>{const end=start+Math.PI*2*(value/total);ctx.beginPath();ctx.arc(cx,cy,r,start,end);ctx.arc(cx,cy,inner,end,start,true);ctx.closePath();ctx.fillStyle=palette[index%palette.length];ctx.fill();start=end});
        let x=18;categories.forEach((name,index)=>{ctx.fillStyle=palette[index%palette.length];ctx.fillRect(x,height-18,8,8);ctx.fillStyle="#687079";ctx.fillText(name,x+12,height-10);x+=ctx.measureText(name).width+34});return;
      }
      const left=48,right=16,top=22,bottom=48,plotW=width-left-right,plotH=height-top-bottom,max=Math.max(...values,1);
      for(let i=0;i<=4;i++){const y=top+plotH*i/4;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();ctx.fillStyle="#8A9298";ctx.fillText(Math.round(max*(1-i/4)).toLocaleString(),4,y+3)}
      if(type==="line"||type==="area"){
        ctx.beginPath();values.forEach((value,index)=>{const x=left+(categories.length===1?plotW/2:index*plotW/(categories.length-1));const y=top+plotH*(1-value/max);index?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.strokeStyle=palette[0];ctx.lineWidth=2.5;ctx.stroke();
      }else{
        const slot=plotW/Math.max(values.length,1),bar=Math.min(34,slot*.62);values.forEach((value,index)=>{const x=left+slot*index+(slot-bar)/2,y=top+plotH*(1-value/max);ctx.fillStyle=palette[0];ctx.fillRect(x,y,bar,top+plotH-y)});
      }
      categories.forEach((name,index)=>{const x=left+(type==="line"?(categories.length===1?plotW/2:index*plotW/(categories.length-1)):(index+.5)*plotW/categories.length);ctx.save();ctx.translate(x,height-bottom+14);if(name.length>9)ctx.rotate(-.32);ctx.textAlign="center";ctx.fillStyle="#687079";ctx.fillText(name.slice(0,18),0,0);ctx.restore()});
    }
    function renderCharts(){
      const root=byId("charts");root.replaceChildren();charts.clear();
      for(const component of payload.dashboard.components.filter(c=>c.type!=="kpi")){
        const card=document.createElement("article");card.className="chart-panel";card.style.gridColumn=`span ${Math.max(4,Math.min(12,component.layout.w))}`;
        const header=document.createElement("header");const eyebrow=document.createElement("p");eyebrow.textContent="ANALYTICAL VIEW";const title=document.createElement("h3");title.textContent=component.title;header.append(eyebrow,title);
        const canvas=document.createElement("canvas");canvas.className="chart";card.append(header,canvas);root.appendChild(card);const data=queryComponent(component);charts.set(component.id,{canvas,component,data});drawChart(canvas,component.type,data);
      }
    }
    function renderInsights(){
      const root=byId("insights");root.replaceChildren();const items=[];
      for(const component of payload.dashboard.components){
        if(items.length>=4)break;
        if(component.type==="kpi"&&component.computation_status==="computed"&&component.computed_value!==null)items.push(`${component.title}: ${formatNumber(component.computed_value,component.style?.unit)}`);
        else if(component.type!=="kpi"){const data=queryComponent(component);if(data.values?.length)items.push(`${data.categories[0]} has the highest displayed value in ${component.title}: ${Intl.NumberFormat("en",{maximumFractionDigits:1}).format(data.values[0])}.`)}
      }
      for(const text of items){const item=document.createElement("p");item.textContent=text;root.appendChild(item)}
    }
    renderFilters();renderKpis();renderCharts();renderInsights();let resizeTimer;window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>charts.forEach(({canvas,component,data})=>drawChart(canvas,component.type,data)),120)});
  </script>
</body>
</html>"""
    replacements = {
        "__TITLE__": html.escape(dashboard.title),
        "__DESCRIPTION__": html.escape(dashboard.description),
        "__COMPANY__": html.escape(dashboard.company_name or "Executive intelligence"),
        "__LOGO__": logo,
        "__PRIMARY__": dashboard.theme.get("primary", "#111827"),
        "__ACCENT__": dashboard.theme.get("accent", "#00ADEF"),
        "__SURFACE__": dashboard.theme.get("surface", "#FFFFFF"),
        "__TEXT__": dashboard.theme.get("text", "#111827"),
        "__STATUS__": html.escape(dashboard.workflow_status.replace("_", " ")),
        "__SCORE__": str(dashboard.quality_score),
        "__PAYLOAD__": payload,
        "__TEMPLATE_CLASS__": template_id,
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    if template_id == "mercedes-hr-executive":
        mercedes_styles = """
  <style>
    body.template-mercedes-hr-executive{background:#e7e9ea;color:#171a1c}
    .template-mercedes-hr-executive .app-header{background:#050607;color:#fff;border:0}
    .template-mercedes-hr-executive .app-brand strong::after{content:"  /  HR INTELLIGENCE";color:#9da5aa;font-size:9px;letter-spacing:.16em}
    .template-mercedes-hr-executive .app-brand span{color:#b9c0c4}
    .template-mercedes-hr-executive .offline-badge{color:#dce1e4;background:#171a1c;border-color:#3e4549}
    .template-mercedes-hr-executive .report-titlebar{border-top:4px solid var(--brand-accent)}
    .template-mercedes-hr-executive .report-page{box-shadow:0 12px 45px rgba(0,0,0,.13)}
    .template-mercedes-hr-executive .filter-strip{background:#202427;border-color:#343a3e}
    .template-mercedes-hr-executive .filter-strip>strong,.template-mercedes-hr-executive .filter-strip label span{color:#d6dade}
    .template-mercedes-hr-executive .kpi-card{border-top-color:#111517}
    .template-mercedes-hr-executive .kpi-card:nth-child(2n){border-top-color:var(--brand-accent)}
    .template-mercedes-hr-executive .eyebrow,.template-mercedes-hr-executive .company-name{color:var(--brand-accent)}
    .template-mercedes-hr-executive .chart-panel{box-shadow:0 2px 8px rgba(24,29,32,.04)}
  </style>"""
        template = template.replace("</head>", f"{mercedes_styles}\n</head>")
    return template


def prepare_dashboard_for_display(dashboard: DashboardSchema) -> DashboardSchema:
    result = dashboard.model_copy(deep=True)
    for filter_spec in result.filters:
        filter_spec.label = filter_spec.field
    for component in result.components:
        if component.type != "kpi":
            continue
        if (
            component.formula
            and component.formula.kind in {"ratio", "period_growth"}
            and component.formula.multiplier == 100
        ):
            component.style["unit"] = "%"
        if component.computation_status is None:
            if component.computed_value is not None:
                component.computation_status = "computed"
            elif component.formula and component.formula.kind == "period_growth":
                component.computation_status = "insufficient_data"
                component.computation_message = (
                    "The matching previous period is missing."
                    if component.computation_evidence.get("required_previous_period")
                    else "Insufficient source periods for this growth KPI."
                )
    result.components = [
        component
        for component in result.components
        if not (
            component.type == "kpi"
            and component.computation_status in {
                "unsupported",
                "insufficient_data",
                "error",
            }
        )
    ]
    component_ids = {component.id for component in result.components}
    result.insights = [
        insight for insight in result.insights if insight.component_id in component_ids
    ]
    return result


def render_dashboard(
    dashboard: DashboardSchema,
    tables: dict[str, pd.DataFrame],
    template_id: str = "generic-executive",
) -> tuple[DashboardSchema, RenderArtifact]:
    from ..services.report_template_service import require_report_template

    require_report_template(template_id)
    result = prepare_dashboard_for_display(dashboard)
    component_data: dict[str, dict[str, Any]] = {}
    for component in result.components:
        if component.type == "kpi":
            component_data[component.id] = {
                "value": component.computed_value,
                "status": component.computation_status,
                "message": component.computation_message,
                "evidence": component.computation_evidence,
            }
        else:
            fixed_filters = (
                component.formula.numerator.filters
                if component.formula
                else {}
            )
            component_data[component.id] = execute_query(
                tables[component.query.table_id],
                component.query,
                fixed_filters,
            )
    result.insights = _derive_insights(result, component_data)

    document = _offline_document(result, component_data, tables, template_id)
    summary = {
        "component_count": len(result.components),
        "filter_count": len(result.filters),
        "component_ids": [component.id for component in result.components],
        "html_bytes": len(document.encode("utf-8")),
        "template_id": template_id,
    }
    return result, RenderArtifact(html=document, component_data=component_data, render_summary=summary)


def _overlap(a: LayoutSchema, b: LayoutSchema) -> bool:
    return not (
        a.x + a.w <= b.x
        or b.x + b.w <= a.x
        or a.y + a.h <= b.y
        or b.y + b.h <= a.y
    )


def evaluate_dashboard(
    dashboard: DashboardSchema,
    data: DataAnalysisSpec,
    business: BusinessAnalysisSpec,
    artifact: RenderArtifact,
    iteration: int,
    max_iterations: int,
) -> EvaluationResult:
    issues: list[EvaluationIssue] = []
    valid_fields = {(column.table_id, column.name) for column in data.semantic_columns}
    numeric_fields = {
        (metric.table_id, metric.field)
        for metric in data.metrics
        if metric.aggregation != "count"
    }
    metric_ids = {kpi.id for kpi in business.kpis}
    kpi_map = {kpi.id: kpi for kpi in business.kpis}

    for index, component in enumerate(dashboard.components):
        if (
            component.type == "kpi"
            and component.computation_status
            and component.computation_status != "computed"
        ):
            issues.append(
                EvaluationIssue(
                    id=f"data-kpi-unavailable-{component.id}",
                    issue_category="data_integrity",
                    severity="high",
                    description=(
                        f"{component.title} has no valid computed value: "
                        f"{component.computation_message or component.computation_status}."
                    ),
                    recommended_action=(
                        "Remove the unsupported KPI or request the missing periods/data; "
                        "never substitute its base aggregate."
                    ),
                    target_agent="data_analyst",
                    component_id=component.id,
                )
            )
        if (component.query.table_id, component.query.metric) not in valid_fields or (
            component.query.group_by
            and (component.query.table_id, component.query.group_by) not in valid_fields
        ):
            issues.append(
                EvaluationIssue(
                    id=f"data-field-{component.id}",
                    issue_category="data_integrity",
                    severity="high",
                    description=f"{component.title} references a field not present in the uploaded dataset.",
                    recommended_action="Rebuild the metric and chart using validated dataset fields.",
                    target_agent="data_analyst",
                    component_id=component.id,
                )
            )
        if (
            component.query.aggregation in {"sum", "avg", "min", "max"}
            and (component.query.table_id, component.query.metric) not in numeric_fields
        ):
            issues.append(
                EvaluationIssue(
                    id=f"data-aggregation-{component.id}",
                    issue_category="data_integrity",
                    severity="high",
                    description=f"{component.query.aggregation} is not supported for {component.query.metric}.",
                    recommended_action="Correct the KPI definition and select a valid aggregation.",
                    target_agent="data_analyst",
                    component_id=component.id,
                )
            )
        if component.metric_id and component.metric_id not in metric_ids:
            issues.append(
                EvaluationIssue(
                    id=f"business-kpi-{component.id}",
                    issue_category="business_requirement",
                    severity="high",
                    description=f"{component.title} is not linked to a validated business KPI.",
                    recommended_action="Align the component with a supported KPI from BusinessAnalysisSpec.",
                    target_agent="business_analyst",
                    component_id=component.id,
                )
            )
        elif component.metric_id:
            expected = kpi_map[component.metric_id]
            if (
                component.query.table_id != expected.table_id
                or component.query.metric != expected.field
                or component.query.aggregation != expected.aggregation
            ):
                issues.append(
                    EvaluationIssue(
                        id=f"data-kpi-consistency-{component.id}",
                        issue_category="data_integrity",
                        severity="high",
                        description=f"{component.title} does not match its validated KPI formula.",
                        recommended_action="Restore the KPI table, field, and aggregation from BusinessAnalysisSpec.",
                        target_agent="business_analyst",
                        component_id=component.id,
                    )
                )
        if component.type == "pie" and len(artifact.component_data.get(component.id, {}).get("categories", [])) > 8:
            issues.append(
                EvaluationIssue(
                    id=f"visual-pie-{component.id}",
                    issue_category="visual",
                    severity="medium",
                    description="The pie chart contains too many categories for reliable comparison.",
                    recommended_action="Limit categories or replace the pie chart with a sorted bar chart.",
                    target_agent="bi_designer",
                    component_id=component.id,
                )
            )
        for other in dashboard.components[index + 1 :]:
            if _overlap(component.layout, other.layout):
                issues.append(
                    EvaluationIssue(
                        id=f"visual-overlap-{component.id}-{other.id}",
                        issue_category="visual",
                        severity="high",
                        description=f"{component.title} overlaps {other.title} in the 12-column layout.",
                        recommended_action="Reflow only the affected components and normalize spacing.",
                        target_agent="bi_designer",
                        component_id=component.id,
                    )
                )

    if not dashboard.components:
        issues.append(
            EvaluationIssue(
                id="business-empty-dashboard",
                issue_category="business_requirement",
                severity="high",
                description="The dashboard has no analytical components.",
                recommended_action="Design components that answer the validated business objectives.",
                target_agent="business_analyst",
            )
        )
    if data.dimensions and not dashboard.filters:
        issues.append(
            EvaluationIssue(
                id="usability-no-filters",
                issue_category="usability",
                severity="medium",
                description="Available dimensions are not exposed as interactive filters.",
                recommended_action="Add a small set of relevant filters using validated dimensions.",
                target_agent="bi_designer",
            )
        )
    if not dashboard.insights:
        issues.append(
            EvaluationIssue(
                id="data-no-grounded-insights",
                issue_category="data_integrity",
                severity="medium",
                description="No insight could be derived from executed chart queries.",
                recommended_action="Review query results and only publish insights backed by computed evidence.",
                target_agent="data_analyst",
            )
        )
    if artifact.dom_metrics.get("horizontalOverflow"):
        issues.append(
            EvaluationIssue(
                id="visual-horizontal-overflow",
                issue_category="visual",
                severity="high",
                description="The rendered dashboard exceeds the viewport width.",
                recommended_action="Reduce component widths and prevent horizontal overflow.",
                target_agent="bi_designer",
            )
        )
    cards = artifact.dom_metrics.get("cards", [])
    kpi_heights = [
        cards[index]["height"]
        for index, component in enumerate(dashboard.components)
        if component.type == "kpi" and index < len(cards)
    ]
    if kpi_heights and max(kpi_heights) - min(kpi_heights) > 8:
        issues.append(
            EvaluationIssue(
                id="visual-kpi-height-consistency",
                issue_category="visual",
                severity="medium",
                description="Rendered KPI cards have inconsistent heights.",
                recommended_action="Normalize KPI card height, padding, and title wrapping.",
                target_agent="bi_designer",
            )
        )
    if artifact.capture_error:
        issues.append(
            EvaluationIssue(
                id="visual-capture-unavailable",
                issue_category="usability",
                severity="low",
                description="Screenshot capture was unavailable for this evaluation run.",
                recommended_action="Install Playwright Chromium to enable full rendered visual evaluation.",
                target_agent="bi_designer",
            )
        )

    deductions = {"low": 1, "medium": 3, "high": 8}
    category_scores = {
        "visual_quality": 50,
        "business_alignment": 25,
        "data_integrity": 15,
        "usability": 10,
    }
    for issue in issues:
        score_key = {
            "visual": "visual_quality",
            "business_requirement": "business_alignment",
            "data_integrity": "data_integrity",
            "usability": "usability",
        }[issue.issue_category]
        category_scores[score_key] -= deductions[issue.severity]
    category_scores = {key: max(value, 0) for key, value in category_scores.items()}
    overall = sum(category_scores.values())
    blocking = any(issue.severity == "high" for issue in issues)
    passed = overall >= 80 and not blocking
    if passed:
        status = "passed"
        route = "publish"
    elif iteration >= max_iterations:
        status = "needs_user_review"
        route = "human_review"
    elif any(issue.issue_category == "data_integrity" for issue in issues):
        status = "needs_refinement"
        route = "refine_data"
    elif any(issue.issue_category == "business_requirement" for issue in issues):
        status = "needs_refinement"
        route = "refine_business"
    else:
        status = "needs_refinement"
        route = "refine_design"
    return EvaluationResult(
        overall_score=overall,
        category_scores=category_scores,
        passed=passed,
        detected_issues=issues,
        status=status,
        iteration=iteration,
        routing_decision=route,
    )


def apply_evaluation_refinement(
    dashboard: DashboardSchema,
    evaluation: EvaluationResult | None,
) -> DashboardSchema:
    if not evaluation:
        return dashboard
    result = deepcopy(dashboard)
    visual_ids = {
        issue.component_id
        for issue in evaluation.detected_issues
        if issue.issue_category in {"visual", "usability"}
    }
    for component in result.components:
        if component.id in visual_ids and component.type == "pie":
            component.type = "bar"
            component.query.limit = min(component.query.limit, 8)
    return normalize_layout(result)
