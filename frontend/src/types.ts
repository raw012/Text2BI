export type ChartType = "kpi" | "bar" | "line" | "pie" | "area" | "table";

export interface DatasetProfile {
  rows: number;
  columns: number;
  metrics: string[];
  dimensions: string[];
  dates: string[];
  column_profiles: Array<{
    name: string;
    dtype: string;
    semantic_type: "metric" | "dimension" | "date" | "identifier";
    null_count: number;
    unique_count: number;
    sample_values: unknown[];
  }>;
}

export interface Dataset {
  id: number;
  name: string;
  row_count: number;
  column_count: number;
  profile: DatasetProfile;
}

export interface DashboardComponent {
  id: string;
  type: ChartType;
  title: string;
  subtitle?: string;
  query: {
    group_by?: string;
    metric: string;
    aggregation: "sum" | "avg" | "count" | "min" | "max" | "distinct_count";
    sort: "asc" | "desc";
    limit: number;
  };
  layout: { x: number; y: number; w: number; h: number };
  style: Record<string, unknown>;
}

export interface Dashboard {
  version: string;
  title: string;
  description: string;
  dataset_id: number;
  theme: Record<string, string>;
  filters: Array<{
    id: string;
    field: string;
    label: string;
    type: "select" | "multi-select" | "date-range" | "number-range";
    options: string[];
  }>;
  components: DashboardComponent[];
  insights: string[];
  quality_score: number;
  critic_notes: string[];
}

export interface ChartData {
  value?: number;
  categories?: string[];
  values?: number[];
}
