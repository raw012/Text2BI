export type ChartType = "kpi" | "bar" | "line" | "pie" | "area" | "table";
export type WorkflowStatus = "draft" | "needs_refinement" | "passed" | "needs_user_review";
export type IssueCategory = "visual" | "data_integrity" | "business_requirement" | "usability";

export interface DatasetProfile {
  rows: number;
  columns: number;
  metrics: string[];
  dimensions: string[];
  dates: string[];
  column_profiles: Array<{
    name: string;
    table_id: string;
    dtype: string;
    semantic_type: "metric" | "dimension" | "date" | "identifier";
    null_count: number;
    unique_count: number;
    sample_values: unknown[];
  }>;
  tables: Array<{
    id: string;
    name: string;
    source_file: string;
    sheet_name?: string;
    rows: number;
    columns: number;
    column_profiles: DatasetProfile["column_profiles"];
    metrics: string[];
    dimensions: string[];
    dates: string[];
  }>;
}

export interface Dataset {
  id: number;
  name: string;
  row_count: number;
  column_count: number;
  profile: DatasetProfile;
}

export interface DatasetPreview {
  dataset_id: number;
  table_id: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
}

export interface DashboardSummary {
  id: number;
  title: string;
  dataset_id: number;
  business_request: string;
  component_count: number;
  filter_count: number;
  status: WorkflowStatus;
  quality_score: number;
  updated_at: string;
}

export interface DashboardComponent {
  id: string;
  type: ChartType;
  title: string;
  subtitle?: string;
  metric_id?: string;
  query: {
    table_id: string;
    group_by?: string;
    metric: string;
    aggregation: "sum" | "avg" | "count" | "min" | "max" | "distinct_count";
    sort: "asc" | "desc";
    limit: number;
  };
  formula?: {
    kind: "aggregate" | "ratio" | "period_growth";
    numerator: {
      table_id: string;
      field: string;
      aggregation: "sum" | "avg" | "count" | "min" | "max" | "distinct_count";
      filters: Record<string, unknown>;
    };
    denominator?: {
      table_id: string;
      field: string;
      aggregation: "sum" | "avg" | "count" | "min" | "max" | "distinct_count";
      filters: Record<string, unknown>;
    };
    time_table_id?: string;
    time_field?: string;
    time_granularity: "none" | "day" | "week" | "month" | "quarter" | "year";
    comparison: "none" | "mom" | "qoq" | "yoy";
    multiplier: number;
  };
  computed_value?: number;
  computation_status?: "computed" | "unsupported" | "insufficient_data" | "error";
  computation_message?: string;
  computation_evidence: Record<string, unknown>;
  layout: { x: number; y: number; w: number; h: number };
  style: Record<string, unknown>;
}

export interface EvaluationIssue {
  id: string;
  issue_category: IssueCategory;
  severity: "low" | "medium" | "high";
  description: string;
  recommended_action: string;
  target_agent: "data_analyst" | "business_analyst" | "bi_designer";
  component_id?: string;
}

export interface EvaluationResult {
  overall_score: number;
  category_scores: Record<string, number>;
  passed: boolean;
  detected_issues: EvaluationIssue[];
  status: WorkflowStatus;
  iteration: number;
  routing_decision: "publish" | "refine_data" | "refine_business" | "refine_design" | "human_review";
}

export interface Dashboard {
  version: string;
  revision: number;
  title: string;
  description: string;
  dataset_id: number;
  company_name?: string;
  logo_url?: string;
  logo_source?: "uploaded" | "official_site" | "custom_mark";
  theme: Record<string, string>;
  filters: Array<{
    id: string;
    field: string;
    table_id: string;
    label: string;
    type: "select" | "multi-select" | "date-range" | "number-range";
    options: string[];
  }>;
  components: DashboardComponent[];
  insights: Array<{
    text: string;
    component_id: string;
    evidence: Record<string, unknown>;
  }>;
  evaluation?: EvaluationResult;
  workflow_status: WorkflowStatus;
  quality_score: number;
  critic_notes: string[];
}

export interface ChartData {
  value?: number;
  categories?: string[];
  values?: number[];
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
}

export interface WorkflowRun {
  run_id: string;
  kind: "generate" | "refine";
  status: "queued" | "running" | "completed" | "failed";
  node: string;
  stage: string;
  message: string;
  progress: number;
  iteration: number;
  max_iterations: number;
  error?: string;
  result?: {
    dashboard_id: number;
    dashboard: Dashboard;
    message?: string;
  };
  created_at: string;
  updated_at: string;
}
