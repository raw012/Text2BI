from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    semantic_type: Literal["metric", "dimension", "date", "identifier"]
    null_count: int
    unique_count: int
    sample_values: list[Any] = []


class DatasetProfile(BaseModel):
    rows: int
    columns: int
    column_profiles: list[ColumnProfile]
    metrics: list[str]
    dimensions: list[str]
    dates: list[str]


class DatasetResponse(BaseModel):
    id: int
    name: str
    row_count: int
    column_count: int
    profile: DatasetProfile


class FilterSchema(BaseModel):
    id: str
    field: str
    label: str
    type: Literal["select", "multi-select", "date-range", "number-range"]
    options: list[str] = []


class QuerySchema(BaseModel):
    group_by: str | None = None
    metric: str
    aggregation: Literal["sum", "avg", "count", "min", "max", "distinct_count"] = "sum"
    sort: Literal["asc", "desc"] = "desc"
    limit: int = 12


class LayoutSchema(BaseModel):
    x: int
    y: int
    w: int
    h: int


class ComponentSchema(BaseModel):
    id: str
    type: Literal["kpi", "bar", "line", "pie", "area", "table"]
    title: str
    subtitle: str | None = None
    query: QuerySchema
    layout: LayoutSchema
    style: dict[str, Any] = {}


class DashboardSchema(BaseModel):
    version: str = "1.0"
    title: str
    description: str
    dataset_id: int
    theme: dict[str, str]
    filters: list[FilterSchema]
    components: list[ComponentSchema]
    insights: list[str]
    quality_score: int = Field(ge=0, le=100)
    critic_notes: list[str]


class GenerateDashboardRequest(BaseModel):
    dataset_id: int
    business_request: str = Field(min_length=3, max_length=2000)


class GenerateDashboardResponse(BaseModel):
    dashboard_id: int
    dashboard: DashboardSchema


class ModifyDashboardRequest(BaseModel):
    dashboard_id: int
    instruction: str | None = None
    dashboard: DashboardSchema | None = None


class InsightsRequest(BaseModel):
    dashboard_id: int
