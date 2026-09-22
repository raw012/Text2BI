from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["low", "medium", "high"]
IssueCategory = Literal["visual", "data_integrity", "business_requirement", "usability"]
TargetAgent = Literal["data_analyst", "business_analyst", "bi_designer"]
WorkflowStatus = Literal["draft", "needs_refinement", "passed", "needs_user_review"]
Aggregation = Literal["sum", "avg", "count", "min", "max", "distinct_count"]
TimeGrain = Literal["none", "day", "week", "month", "quarter", "year"]


class ColumnProfile(BaseModel):
    name: str
    table_id: str = "main"
    dtype: str
    semantic_type: Literal["metric", "dimension", "date", "identifier"]
    null_count: int
    unique_count: int
    sample_values: list[Any] = Field(default_factory=list)


class TableProfile(BaseModel):
    id: str
    name: str
    source_file: str
    sheet_name: str | None = None
    rows: int
    columns: int
    column_profiles: list[ColumnProfile]
    metrics: list[str]
    dimensions: list[str]
    dates: list[str]


class DatasetProfile(BaseModel):
    rows: int
    columns: int
    column_profiles: list[ColumnProfile]
    metrics: list[str]
    dimensions: list[str]
    dates: list[str]
    tables: list[TableProfile] = Field(default_factory=list)


class DatasetResponse(BaseModel):
    id: int
    name: str
    row_count: int
    column_count: int
    profile: DatasetProfile


class DatabaseImportRequest(BaseModel):
    database_url: str = Field(min_length=8, max_length=2000)
    table_name: str = Field(min_length=1, max_length=255)
    schema_name: str | None = Field(default=None, max_length=255)
    dataset_name: str | None = Field(default=None, max_length=255)
    row_limit: int = Field(default=100_000, ge=1, le=500_000)


class FieldRef(BaseModel):
    table_id: str = "main"
    name: str


class QuerySchema(BaseModel):
    table_id: str = "main"
    group_by: str | None = None
    metric: str
    aggregation: Aggregation = "sum"
    sort: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=12, ge=1, le=100)


class DataQualityIssue(BaseModel):
    code: str
    table_id: str = "main"
    column: str | None = None
    severity: Severity
    description: str
    impact: str
    recommended_action: str


class SemanticColumn(BaseModel):
    name: str
    table_id: str = "main"
    semantic_type: Literal["metric", "dimension", "date", "identifier"]
    business_meaning: str
    nullable: bool
    unique_count: int


class MetricDefinition(BaseModel):
    id: str
    name: str
    table_id: str = "main"
    business_meaning: str
    field: str
    aggregation: Aggregation
    required_fields: list[str]
    supported: bool = True


class TimeCapability(BaseModel):
    field: str
    table_id: str = "main"
    valid_ratio: float = Field(ge=0, le=1)
    min_value: str | None = None
    max_value: str | None = None
    supported_comparisons: list[Literal["trend", "mom", "qoq", "yoy"]] = Field(default_factory=list)


class DataAnalysisSpec(BaseModel):
    dataset_summary: str
    row_count: int
    column_count: int
    table_ids: list[str] = Field(default_factory=lambda: ["main"])
    semantic_columns: list[SemanticColumn]
    metrics: list[MetricDefinition]
    dimensions: list[FieldRef]
    time_capabilities: list[TimeCapability]
    quality_report: list[DataQualityIssue]
    analytical_opportunities: list[str]
    duplicate_rows: int = 0


class FormulaOperand(BaseModel):
    table_id: str = "main"
    field: str
    aggregation: Aggregation
    filters: dict[str, Any] = Field(default_factory=dict)


class KPIFormulaSpec(BaseModel):
    kind: Literal["aggregate", "ratio", "period_growth"] = "aggregate"
    numerator: FormulaOperand
    denominator: FormulaOperand | None = None
    time_table_id: str | None = None
    time_field: str | None = None
    time_granularity: TimeGrain = "none"
    comparison: Literal["none", "mom", "qoq", "yoy"] = "none"
    multiplier: float = 1.0


class KPIDefinition(BaseModel):
    id: str
    name: str
    business_meaning: str
    table_id: str = "main"
    field: str
    aggregation: Aggregation
    required_fields: list[str]
    formula: KPIFormulaSpec | None = None
    time_granularity: TimeGrain = "none"
    supported: bool = True
    missing_fields: list[str] = Field(default_factory=list)


class KPIComputationResult(BaseModel):
    kpi_id: str
    status: Literal["computed", "unsupported", "insufficient_data", "error"]
    value: float | int | None = None
    current_value: float | int | None = None
    previous_value: float | int | None = None
    change_rate: float | None = None
    series: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class KPIResultSet(BaseModel):
    results: list[KPIComputationResult]


class BusinessAnalysisSpec(BaseModel):
    audience: str
    business_objectives: list[str]
    kpis: list[KPIDefinition]
    comparison_requirements: list[str]
    business_questions: list[str]
    dashboard_priorities: list[str]
    additional_data_required: list[str] = Field(default_factory=list)


class FilterSchema(BaseModel):
    id: str
    field: str
    table_id: str = "main"
    label: str
    type: Literal["select", "multi-select", "date-range", "number-range"]
    options: list[str] = Field(default_factory=list)


class LayoutSchema(BaseModel):
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1, le=20)


class ComponentSchema(BaseModel):
    id: str
    type: Literal["kpi", "bar", "line", "pie", "area", "table"]
    title: str
    subtitle: str | None = None
    metric_id: str | None = None
    query: QuerySchema
    formula: KPIFormulaSpec | None = None
    computed_value: float | int | None = None
    computation_status: Literal[
        "computed", "unsupported", "insufficient_data", "error"
    ] | None = None
    computation_message: str | None = None
    computation_evidence: dict[str, Any] = Field(default_factory=dict)
    layout: LayoutSchema
    style: dict[str, Any] = Field(default_factory=dict)


class InsightSchema(BaseModel):
    text: str
    component_id: str
    evidence: dict[str, Any]


class EvaluationIssue(BaseModel):
    id: str
    issue_category: IssueCategory
    severity: Severity
    description: str
    recommended_action: str
    target_agent: TargetAgent
    component_id: str | None = None


class EvaluationResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    category_scores: dict[str, int]
    passed: bool
    detected_issues: list[EvaluationIssue]
    status: WorkflowStatus
    iteration: int = Field(ge=1, le=5)
    routing_decision: Literal[
        "publish", "refine_data", "refine_business", "refine_design", "human_review"
    ]


class DashboardSchema(BaseModel):
    version: str = "2.1"
    revision: int = Field(default=1, ge=1)
    title: str
    description: str
    dataset_id: int
    company_name: str | None = None
    logo_url: str | None = None
    logo_source: Literal["uploaded", "official_site", "custom_mark"] | None = None
    theme: dict[str, str]
    filters: list[FilterSchema]
    components: list[ComponentSchema]
    insights: list[InsightSchema] = Field(default_factory=list)
    evaluation: EvaluationResult | None = None
    workflow_status: WorkflowStatus = "draft"
    quality_score: int = Field(default=0, ge=0, le=100)
    critic_notes: list[str] = Field(default_factory=list)


class RenderArtifact(BaseModel):
    html: str
    component_data: dict[str, dict[str, Any]]
    render_summary: dict[str, Any]
    screenshot_base64: str | None = None
    dom_metrics: dict[str, Any] = Field(default_factory=dict)
    capture_error: str | None = None


class VisualReview(BaseModel):
    summary: str
    issues: list[EvaluationIssue] = Field(default_factory=list)


class BrandIdentitySpec(BaseModel):
    company_name: str | None = None
    website_domain: str | None = None
    primary_color: str = "#111827"
    accent_color: str = "#00ADEF"
    initials: str = "BI"
    confidence: float = Field(default=0, ge=0, le=1)


class GenerateDashboardRequest(BaseModel):
    dataset_id: int
    business_request: str = Field(min_length=3, max_length=2000)
    logo_url: str | None = None
    user_preferences: str | None = Field(default=None, max_length=1000)


class GenerateDashboardResponse(BaseModel):
    dashboard_id: int
    dashboard: DashboardSchema


class ModifyDashboardRequest(BaseModel):
    dashboard_id: int
    instruction: str | None = None
    dashboard: DashboardSchema | None = None


class ChatRefinementRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


class ChatRefinementResponse(BaseModel):
    dashboard_id: int
    message: str
    dashboard: DashboardSchema


class InsightsRequest(BaseModel):
    dashboard_id: int
