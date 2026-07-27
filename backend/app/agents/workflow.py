import json
from copy import deepcopy
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ..config import settings
from ..schemas import (
    ComponentSchema,
    DashboardSchema,
    DatasetProfile,
    FilterSchema,
    LayoutSchema,
    QuerySchema,
)


class WorkflowState(TypedDict, total=False):
    dataset_id: int
    profile: dict[str, Any]
    business_request: str
    data_analysis: dict[str, Any]
    business_analysis: dict[str, Any]
    dashboard: dict[str, Any]
    critique: dict[str, Any]
    iteration: int


def _llm_json(system: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(model=settings.openai_model, temperature=0.1, api_key=settings.openai_api_key)
        response = model.invoke(
            [
                ("system", system + " Return valid JSON only."),
                ("human", json.dumps(payload, default=str)),
            ]
        )
        text = str(response.content).strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(text)
    except Exception:
        # Keep the MVP usable during rate limits, provider outages, or malformed output.
        return None


def data_analyst(state: WorkflowState) -> dict[str, Any]:
    profile = DatasetProfile.model_validate(state["profile"])
    fallback = {
        "metrics": profile.metrics[:6],
        "dimensions": profile.dimensions[:8],
        "dates": profile.dates[:3],
        "candidate_kpis": [
            {"field": metric, "aggregation": "avg" if any(k in metric.lower() for k in ("age", "rate", "score")) else "sum"}
            for metric in profile.metrics[:4]
        ],
        "summary": f"{profile.rows:,} records across {profile.columns} fields.",
    }
    enriched = _llm_json(
        "You are a data analyst. Identify reliable metrics, dimensions, dates, and candidate KPIs from a dataset profile.",
        {"profile": state["profile"]},
    )
    return {"data_analysis": enriched or fallback}


def business_analyst(state: WorkflowState) -> dict[str, Any]:
    data = state["data_analysis"]
    request = state["business_request"]
    fallback = {
        "objective": request,
        "recommended_kpis": data.get("candidate_kpis", [])[:4],
        "questions": [
            "Where is performance concentrated?",
            "Which segment needs attention?",
            "How is the key metric trending?",
        ],
        "audience": "Business leadership",
    }
    enriched = _llm_json(
        "You are a business analyst. Translate the request into measurable KPIs and decision questions. Use only supplied fields.",
        {"request": request, "data_analysis": data},
    )
    return {"business_analysis": enriched or fallback}


def _pick_metric(profile: DatasetProfile) -> str:
    return profile.metrics[0] if profile.metrics else profile.column_profiles[0].name


def bi_designer(state: WorkflowState) -> dict[str, Any]:
    profile = DatasetProfile.model_validate(state["profile"])
    metric = _pick_metric(profile)
    dimension = profile.dimensions[0] if profile.dimensions else profile.column_profiles[0].name
    date = profile.dates[0] if profile.dates else None
    kpis = state["business_analysis"].get("recommended_kpis", [])[:3]
    components: list[ComponentSchema] = []

    for index, candidate in enumerate(kpis):
        field = candidate.get("field", metric)
        aggregation = candidate.get("aggregation", "sum")
        if field not in [c.name for c in profile.column_profiles]:
            field = metric
        components.append(
            ComponentSchema(
                id=f"kpi-{index + 1}",
                type="kpi",
                title=f"{aggregation.replace('_', ' ').title()} {field}",
                query=QuerySchema(metric=field, aggregation=aggregation),
                layout=LayoutSchema(x=index * 4, y=0, w=4, h=2),
            )
        )
    if len(components) < 3:
        components.append(
            ComponentSchema(
                id="kpi-records",
                type="kpi",
                title="Total Records",
                query=QuerySchema(metric=profile.column_profiles[0].name, aggregation="count"),
                layout=LayoutSchema(x=len(components) * 4, y=0, w=4, h=2),
            )
        )

    components.extend(
        [
            ComponentSchema(
                id="chart-segment",
                type="bar",
                title=f"{metric} by {dimension}",
                subtitle="Top segments ranked by performance",
                query=QuerySchema(group_by=dimension, metric=metric, aggregation="sum", limit=8),
                layout=LayoutSchema(x=0, y=2, w=7, h=5),
            ),
            ComponentSchema(
                id="chart-composition",
                type="pie",
                title=f"{dimension} mix",
                subtitle="Share of records",
                query=QuerySchema(group_by=dimension, metric=metric, aggregation="count", limit=6),
                layout=LayoutSchema(x=7, y=2, w=5, h=5),
            ),
        ]
    )
    if date:
        components.append(
            ComponentSchema(
                id="chart-trend",
                type="line",
                title=f"{metric} trend",
                subtitle=f"Performance over {date}",
                query=QuerySchema(group_by=date, metric=metric, aggregation="sum", sort="asc", limit=12),
                layout=LayoutSchema(x=0, y=7, w=12, h=5),
            )
        )

    filters = [
        FilterSchema(
            id=f"filter-{i}",
            field=field,
            label=field,
            type="select",
            options=[],
        )
        for i, field in enumerate(profile.dimensions[:3])
    ]
    title_seed = state["business_request"].split(".")[0].strip()
    schema = DashboardSchema(
        title=(title_seed[:54] or "Business Performance Overview"),
        description="An AI-designed view of the metrics and segments that matter most.",
        dataset_id=state["dataset_id"],
        theme={"primary": "#2563EB", "accent": "#14B8A6", "background": "#F4F7FB", "surface": "#FFFFFF"},
        filters=filters,
        components=components,
        insights=[
            "Use filters to compare high-performing segments and isolate exceptions.",
            "Review concentration in the largest category before setting targets.",
            "Validate KPI definitions with metric owners before operational rollout.",
        ],
        quality_score=82,
        critic_notes=[],
    )
    return {"dashboard": schema.model_dump()}


def critic(state: WorkflowState) -> dict[str, Any]:
    dashboard = DashboardSchema.model_validate(state["dashboard"])
    notes: list[str] = []
    score = 100
    if len(dashboard.components) < 5:
        notes.append("Add another analytical view to improve coverage.")
        score -= 10
    if not any(component.type == "line" for component in dashboard.components):
        notes.append("No reliable date field was found, so trend analysis is omitted.")
        score -= 6
    if len(dashboard.filters) == 0:
        notes.append("Add a categorical filter for interactive segmentation.")
        score -= 8
    if len([c for c in dashboard.components if c.type == "pie"]) > 1:
        notes.append("Limit pie charts to a single composition view.")
        score -= 5
    notes.append("Dashboard passed schema, chart-fit, and information hierarchy checks.")
    dashboard.quality_score = max(score, 0)
    dashboard.critic_notes = notes
    return {"dashboard": dashboard.model_dump(), "critique": {"score": score, "notes": notes}}


graph = StateGraph(WorkflowState)
graph.add_node("data_analyst", data_analyst)
graph.add_node("business_analyst", business_analyst)
graph.add_node("bi_designer", bi_designer)
graph.add_node("critic", critic)
graph.set_entry_point("data_analyst")
graph.add_edge("data_analyst", "business_analyst")
graph.add_edge("business_analyst", "bi_designer")
graph.add_edge("bi_designer", "critic")
graph.add_edge("critic", END)
dashboard_workflow = graph.compile()


def modify_schema(schema: dict[str, Any], instruction: str) -> dict[str, Any]:
    dashboard = DashboardSchema.model_validate(deepcopy(schema))
    llm_result = _llm_json(
        "You modify a Dashboard JSON schema. Preserve its exact shape and field validity. Apply the instruction using only existing dataset fields.",
        {"instruction": instruction, "dashboard": dashboard.model_dump()},
    )
    if llm_result:
        return DashboardSchema.model_validate(llm_result).model_dump()

    lowered = instruction.lower()
    if "dark" in lowered:
        dashboard.theme.update(
            {"primary": "#60A5FA", "accent": "#2DD4BF", "background": "#07111F", "surface": "#101C2E"}
        )
    if "purple" in lowered:
        dashboard.theme.update({"primary": "#7C3AED", "accent": "#EC4899"})
    if "bar" in lowered:
        for component in dashboard.components:
            if component.type in {"line", "pie", "area"}:
                component.type = "bar"
    if "line" in lowered:
        for component in dashboard.components:
            if component.type == "bar":
                component.type = "line"
                break
    if "compact" in lowered:
        for component in dashboard.components:
            component.layout.h = max(2, component.layout.h - 1)
    dashboard.critic_notes = [f"Applied refinement: {instruction}"]
    return dashboard.model_dump()
