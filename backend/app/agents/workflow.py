from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ..agent_tools.analysis import analyze_dataset, validate_data_analysis
from ..agent_tools.business import build_business_fallback, validate_business_analysis
from ..agent_tools.dashboard import (
    apply_evaluation_refinement,
    apply_user_instruction,
    build_dashboard_fallback,
    evaluate_dashboard,
    normalize_layout,
    render_dashboard,
)
from ..agent_tools.kpi import calculate_kpis
from ..config import settings
from ..schemas import (
    BusinessAnalysisSpec,
    DashboardSchema,
    DataAnalysisSpec,
    EvaluationResult,
    KPIResultSet,
    RenderArtifact,
    VisualReview,
)
from ..services.data_service import read_dataset_tables
from ..services.llm_service import qwen_structured, qwen_vision_structured
from ..services.visual_service import capture_dashboard_html
from ..services.workflow_progress import update_workflow_run


class WorkflowState(TypedDict, total=False):
    run_id: str
    dataset_id: int
    dataset_file_path: str
    profile: dict[str, Any]
    business_request: str
    logo_url: str | None
    logo_source: str | None
    brand_identity: dict[str, Any] | None
    user_preferences: str | None
    user_feedback: str | None
    current_dashboard: dict[str, Any] | None
    data_analysis: dict[str, Any]
    business_analysis: dict[str, Any]
    kpi_results: dict[str, Any]
    dashboard: dict[str, Any]
    render_artifact: dict[str, Any]
    evaluation: dict[str, Any]
    iteration: int
    route_hint: str


def request_router(state: WorkflowState) -> dict[str, Any]:
    update_workflow_run(
        state.get("run_id"),
        status="running",
        node="request_router",
        stage="Understanding your request",
        message="Routing the request to the right analyst.",
        progress=4,
    )
    if not state.get("current_dashboard"):
        return {"route_hint": "data"}
    feedback = (state.get("user_feedback") or "").lower()
    if any(
        token in feedback
        for token in (
            "数据",
            "字段",
            "计算",
            "公式",
            "聚合",
            "平均",
            "总和",
            "data",
            "field",
            "formula",
            "aggregation",
        )
    ):
        route = "data"
    elif any(
        token in feedback
        for token in (
            "业务",
            "目标",
            "kpi",
            "受众",
            "高管",
            "business",
            "objective",
            "audience",
        )
    ):
        route = "business"
    else:
        route = "design"
    return {
        "route_hint": route,
        "dashboard": state["current_dashboard"],
        "iteration": 0,
    }


def route_request(state: WorkflowState) -> str:
    return state["route_hint"]


def data_analyst(state: WorkflowState) -> dict[str, Any]:
    iteration = state.get("iteration", 0)
    update_workflow_run(
        state.get("run_id"),
        node="data_analyst",
        stage="Data Analyst",
        message="Profiling tables, fields, missing values, duplicates, and usable metrics.",
        progress=min(90, 5 + iteration * 18),
        iteration=iteration,
    )
    tables = read_dataset_tables(state["dataset_file_path"])
    deterministic = analyze_dataset(tables, state["profile"])
    enriched = qwen_structured(
        "data_analysis",
        "Review and enrich the deterministic dataset analysis. Preserve every calculated fact.",
        {
            "profile": state["profile"],
            "deterministic_analysis": deterministic.model_dump(mode="json"),
            "user_request": state["business_request"],
            "evaluation_feedback": state.get("evaluation"),
            "user_feedback": state.get("user_feedback"),
        },
        DataAnalysisSpec,
    )
    spec = validate_data_analysis(enriched or deterministic, state["profile"])
    return {"data_analysis": spec.model_dump(mode="json")}


def business_analyst(state: WorkflowState) -> dict[str, Any]:
    iteration = state.get("iteration", 0)
    update_workflow_run(
        state.get("run_id"),
        node="business_analyst",
        stage="Business Analyst",
        message="Defining the decision goal and the core KPIs supported by your data.",
        progress=min(92, 8 + iteration * 18),
        iteration=iteration,
    )
    data = DataAnalysisSpec.model_validate(state["data_analysis"])
    fallback = build_business_fallback(state["business_request"], data)
    planned = qwen_structured(
        "business_analysis",
        "Translate the request into supported KPI definitions and business questions.",
        {
            "request": state["business_request"],
            "user_feedback": state.get("user_feedback"),
            "data_analysis": data.model_dump(mode="json"),
            "evaluation_feedback": state.get("evaluation"),
        },
        BusinessAnalysisSpec,
    )
    spec = validate_business_analysis(
        planned or fallback,
        data,
        request=state["business_request"],
    )
    return {"business_analysis": spec.model_dump(mode="json")}


def kpi_calculator(state: WorkflowState) -> dict[str, Any]:
    iteration = state.get("iteration", 0)
    update_workflow_run(
        state.get("run_id"),
        node="kpi_calculator",
        stage="KPI calculation",
        message="Calculating validated KPI values with Python.",
        progress=min(94, 11 + iteration * 18),
        iteration=iteration,
    )
    data = DataAnalysisSpec.model_validate(state["data_analysis"])
    business = BusinessAnalysisSpec.model_validate(state["business_analysis"])
    tables = read_dataset_tables(state["dataset_file_path"])
    results = calculate_kpis(business.kpis, tables, data)
    return {"kpi_results": results.model_dump(mode="json")}


def _candidate_is_data_safe(
    candidate: DashboardSchema,
    data: DataAnalysisSpec,
    business: BusinessAnalysisSpec,
) -> bool:
    fields = {(column.table_id, column.name) for column in data.semantic_columns}
    metric_ids = {kpi.id for kpi in business.kpis}
    required_kpis = {kpi.id for kpi in business.kpis[: min(4, len(business.kpis))]}
    represented_kpis = {
        component.metric_id
        for component in candidate.components
        if component.type == "kpi" and component.metric_id
    }
    return (
        candidate.dataset_id > 0
        and required_kpis.issubset(represented_kpis)
        and all(
            (component.query.table_id, component.query.metric) in fields
            and (
                not component.query.group_by
                or (component.query.table_id, component.query.group_by) in fields
            )
            and (not component.metric_id or component.metric_id in metric_ids)
            for component in candidate.components
        )
        and all(
            (filter_item.table_id, filter_item.field) in fields
            for filter_item in candidate.filters
        )
    )


def bi_designer(state: WorkflowState) -> dict[str, Any]:
    iteration = state.get("iteration", 0)
    update_workflow_run(
        state.get("run_id"),
        node="bi_designer",
        stage="BI Designer",
        message=(
            "Refining the dashboard from evaluation feedback."
            if iteration
            else "Building a KPI-first dashboard layout."
        ),
        progress=min(95, 14 + iteration * 18),
        iteration=iteration,
    )
    data = DataAnalysisSpec.model_validate(state["data_analysis"])
    business = BusinessAnalysisSpec.model_validate(state["business_analysis"])
    kpi_results = (
        KPIResultSet.model_validate(state["kpi_results"])
        if state.get("kpi_results")
        else calculate_kpis(
            business.kpis,
            read_dataset_tables(state["dataset_file_path"]),
            data,
        )
    )
    existing_payload = state.get("dashboard") or state.get("current_dashboard")

    if existing_payload:
        existing = DashboardSchema.model_validate(existing_payload)
        existing.evaluation = None
        existing.workflow_status = "draft"
        existing.quality_score = 0
        existing.critic_notes = []
        required_kpis = {kpi.id for kpi in business.kpis[: min(4, len(business.kpis))]}
        represented_kpis = {
            component.metric_id
            for component in existing.components
            if component.type == "kpi" and component.metric_id
        }
        if not required_kpis.issubset(represented_kpis):
            fallback = build_dashboard_fallback(
                dataset_id=state["dataset_id"],
                request=state["business_request"],
                data=data,
                business=business,
                kpi_results=kpi_results,
                logo_url=state.get("logo_url"),
                preferences=state.get("user_preferences"),
                brand_identity=state.get("brand_identity"),
                logo_source=state.get("logo_source"),
                revision=existing.revision + 1,
            )
        elif state.get("user_feedback"):
            fallback = apply_user_instruction(existing, state["user_feedback"] or "", data)
        else:
            fallback = apply_evaluation_refinement(
                existing,
                EvaluationResult.model_validate(state["evaluation"])
                if state.get("evaluation")
                else None,
            )
    else:
        fallback = build_dashboard_fallback(
            dataset_id=state["dataset_id"],
            request=state["business_request"],
            data=data,
            business=business,
            kpi_results=kpi_results,
            logo_url=state.get("logo_url"),
            preferences=state.get("user_preferences"),
            brand_identity=state.get("brand_identity"),
            logo_source=state.get("logo_source"),
        )

    designed = qwen_structured(
        "bi_design",
        "Design or refine only the affected dashboard components. Return DashboardSchema, never HTML.",
        {
            "request": state["business_request"],
            "user_feedback": state.get("user_feedback"),
            "data_analysis": data.model_dump(mode="json"),
            "business_analysis": business.model_dump(mode="json"),
            "kpi_results": kpi_results.model_dump(mode="json"),
            "current_dashboard": fallback.model_dump(mode="json"),
            "evaluation_feedback": state.get("evaluation"),
        },
        DashboardSchema,
    )
    candidate = designed if designed and _candidate_is_data_safe(designed, data, business) else fallback
    candidate.dataset_id = state["dataset_id"]
    candidate.logo_url = state.get("logo_url") or candidate.logo_url
    candidate.logo_source = state.get("logo_source") or candidate.logo_source
    if state.get("brand_identity"):
        identity = state["brand_identity"] or {}
        candidate.company_name = identity.get("company_name")
        candidate.theme.update(
            {
                "primary": identity.get("primary_color", candidate.theme.get("primary", "#111827")),
                "accent": identity.get("accent_color", candidate.theme.get("accent", "#00ADEF")),
            }
        )
    result_map = {result.kpi_id: result for result in kpi_results.results}
    kpi_map = {kpi.id: kpi for kpi in business.kpis}
    for component in candidate.components:
        if component.metric_id in kpi_map:
            kpi = kpi_map[component.metric_id]
            component.formula = kpi.formula
            computed = result_map.get(component.metric_id)
            if computed:
                component.computation_status = computed.status
                component.computation_message = computed.message
                component.computation_evidence = computed.evidence
                component.computed_value = (
                    computed.value if computed.status == "computed" else None
                )
            if (
                kpi.formula
                and kpi.formula.kind in {"ratio", "period_growth"}
                and kpi.formula.multiplier == 100
            ):
                component.style["unit"] = "%"
    candidate.components = [
        component
        for component in candidate.components
        if not (
            component.type == "kpi"
            and component.metric_id in result_map
            and result_map[component.metric_id].status != "computed"
        )
    ]
    candidate.insights = []
    candidate.evaluation = None
    candidate.workflow_status = "draft"
    candidate = normalize_layout(candidate)
    return {"dashboard": candidate.model_dump(mode="json")}


def render_preview(state: WorkflowState) -> dict[str, Any]:
    update_workflow_run(
        state.get("run_id"),
        node="render_preview",
        stage="Dashboard render",
        message="Rendering charts and capturing the dashboard for visual review.",
        progress=min(96, 16 + state.get("iteration", 0) * 18),
        iteration=state.get("iteration", 0),
    )
    dashboard = DashboardSchema.model_validate(state["dashboard"])
    tables = read_dataset_tables(state["dataset_file_path"])
    rendered_dashboard, artifact = render_dashboard(dashboard, tables)
    screenshot, dom_metrics, capture_error = capture_dashboard_html(artifact.html)
    artifact.screenshot_base64 = screenshot
    artifact.dom_metrics = dom_metrics
    artifact.capture_error = capture_error
    return {
        "dashboard": rendered_dashboard.model_dump(mode="json"),
        "render_artifact": artifact.model_dump(mode="json"),
    }


def bi_evaluator(state: WorkflowState) -> dict[str, Any]:
    iteration = min(state.get("iteration", 0) + 1, settings.max_workflow_iterations)
    update_workflow_run(
        state.get("run_id"),
        node="bi_evaluator",
        stage="BI Evaluation",
        message=f"Checking data, requirements, layout, and visual quality · iteration {iteration}/5.",
        progress=min(98, 18 + (iteration - 1) * 18),
        iteration=iteration,
    )
    dashboard = DashboardSchema.model_validate(state["dashboard"])
    data = DataAnalysisSpec.model_validate(state["data_analysis"])
    business = BusinessAnalysisSpec.model_validate(state["business_analysis"])
    artifact = RenderArtifact.model_validate(state["render_artifact"])

    deterministic = evaluate_dashboard(
        dashboard,
        data,
        business,
        artifact,
        iteration=iteration,
        max_iterations=settings.max_workflow_iterations,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        qwen_future = executor.submit(
            qwen_structured,
            "bi_evaluation",
            "Review requirement alignment only. Do not redesign and do not override deterministic data checks.",
            {
                "user_request": state["business_request"],
                "business_analysis": business.model_dump(mode="json"),
                "dashboard": dashboard.model_dump(mode="json"),
                "render_summary": artifact.render_summary,
                "deterministic_evaluation": deterministic.model_dump(mode="json"),
            },
            EvaluationResult,
        )
        visual_future = executor.submit(
            qwen_vision_structured,
            "bi_evaluation",
            "Evaluate the rendered BI dashboard screenshot for layout, typography, branding, hierarchy, and usability.",
            {
                "user_request": state["business_request"],
                "render_summary": artifact.render_summary,
                "dom_metrics": artifact.dom_metrics,
                "dashboard_title": dashboard.title,
                "user_preferences": state.get("user_preferences"),
            },
            artifact.screenshot_base64,
            VisualReview,
        )
        qwen_review = qwen_future.result()
        visual_review = visual_future.result()
    # Qwen may add visual/business observations, but deterministic validation owns
    # data integrity, iteration count, routing, and publication status.
    if qwen_review:
        known_ids = {issue.id for issue in deterministic.detected_issues}
        added = False
        for issue in qwen_review.detected_issues:
            if issue.id not in known_ids and issue.issue_category != "data_integrity":
                if iteration >= 2 and issue.severity == "high":
                    issue.severity = "medium"
                deterministic.detected_issues.append(issue)
                added = True
        if added:
            deductions = {"low": 1, "medium": 3, "high": 8}
            scores = {
                "visual_quality": 50,
                "business_alignment": 25,
                "data_integrity": deterministic.category_scores["data_integrity"],
                "usability": 10,
            }
            for issue in deterministic.detected_issues:
                if issue.issue_category != "data_integrity":
                    score_key = {
                        "visual": "visual_quality",
                        "business_requirement": "business_alignment",
                        "usability": "usability",
                    }[issue.issue_category]
                    scores[score_key] -= deductions[issue.severity]
            deterministic.category_scores = {
                category: max(score, 0) for category, score in scores.items()
            }
            deterministic.overall_score = sum(deterministic.category_scores.values())
            blocking = any(issue.severity == "high" for issue in deterministic.detected_issues)
            if deterministic.overall_score >= 80 and not blocking:
                deterministic.passed = True
                deterministic.status = "passed"
                deterministic.routing_decision = "publish"
            elif iteration >= settings.max_workflow_iterations:
                deterministic.passed = False
                deterministic.status = "needs_user_review"
                deterministic.routing_decision = "human_review"
            else:
                deterministic.passed = False
                deterministic.status = "needs_refinement"
                categories = {
                    issue.issue_category for issue in deterministic.detected_issues
                }
                if "data_integrity" in categories:
                    deterministic.routing_decision = "refine_data"
                elif "business_requirement" in categories:
                    deterministic.routing_decision = "refine_business"
                else:
                    deterministic.routing_decision = "refine_design"
    if visual_review:
        known_ids = {issue.id for issue in deterministic.detected_issues}
        for issue in visual_review.issues:
            if (
                issue.id not in known_ids
                and issue.issue_category in {"visual", "usability"}
            ):
                if iteration >= 2 and issue.severity == "high":
                    issue.severity = "medium"
                deterministic.detected_issues.append(issue)
        # Reuse deterministic scoring/routing by applying the same bounded deductions.
        scores = {
            "visual_quality": 50,
            "business_alignment": deterministic.category_scores["business_alignment"],
            "data_integrity": deterministic.category_scores["data_integrity"],
            "usability": 10,
        }
        deductions = {"low": 1, "medium": 3, "high": 8}
        for issue in deterministic.detected_issues:
            if issue.issue_category == "visual":
                scores["visual_quality"] -= deductions[issue.severity]
            elif issue.issue_category == "usability":
                scores["usability"] -= deductions[issue.severity]
        deterministic.category_scores = {
            category: max(score, 0) for category, score in scores.items()
        }
        deterministic.overall_score = sum(deterministic.category_scores.values())
        blocking = any(issue.severity == "high" for issue in deterministic.detected_issues)
        deterministic.passed = deterministic.overall_score >= 80 and not blocking
        if deterministic.passed:
            deterministic.status = "passed"
            deterministic.routing_decision = "publish"
        elif iteration >= settings.max_workflow_iterations:
            deterministic.status = "needs_user_review"
            deterministic.routing_decision = "human_review"
        else:
            deterministic.status = "needs_refinement"
            categories = {
                issue.issue_category for issue in deterministic.detected_issues
            }
            if "data_integrity" in categories:
                deterministic.routing_decision = "refine_data"
            elif "business_requirement" in categories:
                deterministic.routing_decision = "refine_business"
            else:
                deterministic.routing_decision = "refine_design"

    dashboard.evaluation = deterministic
    dashboard.workflow_status = deterministic.status
    dashboard.quality_score = deterministic.overall_score
    dashboard.critic_notes = [
        f"[{issue.severity}] {issue.description} → {issue.recommended_action}"
        for issue in deterministic.detected_issues
    ] or ["Dashboard passed visual, data, requirement, and usability validation."]
    next_stage = {
        "publish": "Dashboard approved",
        "human_review": "Publishing best available result",
        "refine_data": "Returning to Data Analyst",
        "refine_business": "Returning to Business Analyst",
        "refine_design": "Returning to BI Designer",
    }[deterministic.routing_decision]
    update_workflow_run(
        state.get("run_id"),
        stage=next_stage,
        message=(
            "Evaluation passed. Preparing the result."
            if deterministic.routing_decision == "publish"
            else (
                "Five iterations completed. Publishing the best result for your review."
                if deterministic.routing_decision == "human_review"
                else f"Evaluation found issues. {next_stage} for targeted refinement."
            )
        ),
        iteration=iteration,
        progress=96 if deterministic.routing_decision in {"publish", "human_review"} else 90,
    )
    return {
        "dashboard": dashboard.model_dump(mode="json"),
        "evaluation": deterministic.model_dump(mode="json"),
        "iteration": iteration,
    }


def route_evaluation(state: WorkflowState) -> str:
    evaluation = EvaluationResult.model_validate(state["evaluation"])
    return evaluation.routing_decision


graph = StateGraph(WorkflowState)
graph.add_node("request_router", request_router)
graph.add_node("data_analyst", data_analyst)
graph.add_node("business_analyst", business_analyst)
graph.add_node("kpi_calculator", kpi_calculator)
graph.add_node("bi_designer", bi_designer)
graph.add_node("render_preview", render_preview)
graph.add_node("bi_evaluator", bi_evaluator)

graph.set_entry_point("request_router")
graph.add_conditional_edges(
    "request_router",
    route_request,
    {
        "data": "data_analyst",
        "business": "business_analyst",
        "design": "bi_designer",
    },
)
graph.add_edge("data_analyst", "business_analyst")
graph.add_edge("business_analyst", "kpi_calculator")
graph.add_edge("kpi_calculator", "bi_designer")
graph.add_edge("bi_designer", "render_preview")
graph.add_edge("render_preview", "bi_evaluator")
graph.add_conditional_edges(
    "bi_evaluator",
    route_evaluation,
    {
        "publish": END,
        "human_review": END,
        "refine_data": "data_analyst",
        "refine_business": "business_analyst",
        "refine_design": "bi_designer",
    },
)

dashboard_workflow = graph.compile()
