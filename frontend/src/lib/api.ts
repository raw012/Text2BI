import type { ChartData, ChatMessage, Dashboard, DashboardSummary, Dataset, DatasetPreview, WorkflowRun } from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Something went wrong." }));
    throw new Error(body.detail || "Request failed.");
  }
  return response.json();
}

export const api = {
  datasets() {
    return request<Dataset[]>("/datasets");
  },
  dashboards() {
    return request<{ dashboards: DashboardSummary[] }>("/dashboards");
  },
  dataset(datasetId: number) {
    return request<Dataset>(`/datasets/${datasetId}`);
  },
  datasetPreview(datasetId: number, tableId?: string) {
    const params = new URLSearchParams({ limit: "25" });
    if (tableId) params.set("table_id", tableId);
    return request<DatasetPreview>(`/datasets/${datasetId}/preview?${params}`);
  },
  replaceDataset(datasetId: number, files: File[]) {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return request<Dataset>(`/datasets/${datasetId}/replace`, { method: "POST", body });
  },
  connectDatabase(payload: { database_url: string; table_name: string; schema_name?: string; dataset_name?: string }) {
    return request<Dataset>("/connect_database", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  connectCuratedTlc(table: "tlc_daily" | "tlc_pickup_zone") {
    return request<Dataset>(`/datasets/connect_curated_tlc?table=${table}`, { method: "POST" });
  },
  upload(files: File[]) {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return request<Dataset>("/upload_dataset", { method: "POST", body });
  },
  uploadLogo(file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<{ logo_url: string }>("/upload_logo", { method: "POST", body });
  },
  generate(datasetId: number, businessRequest: string, logoUrl?: string, userPreferences?: string) {
    return request<{ dashboard_id: number; dashboard: Dashboard }>("/generate_dashboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        business_request: businessRequest,
        logo_url: logoUrl || null,
        user_preferences: userPreferences || null,
      }),
    });
  },
  startGenerate(datasetId: number, businessRequest: string, logoUrl?: string) {
    return request<WorkflowRun>("/workflow_runs/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        business_request: businessRequest,
        logo_url: logoUrl || null,
      }),
    });
  },
  startRefinement(dashboardId: number, message: string) {
    return request<WorkflowRun>(`/dashboards/${dashboardId}/workflow_runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  },
  workflowRun(runId: string) {
    return request<WorkflowRun>(`/workflow_runs/${runId}`);
  },
  dashboard(dashboardId: number) {
    return request<{ dashboard_id: number; dashboard: Dashboard }>(`/dashboards/${dashboardId}`);
  },
  async waitForRun(runId: string, onUpdate: (run: WorkflowRun) => void) {
    const deadline = Date.now() + 15 * 60 * 1000;
    while (Date.now() < deadline) {
      const run = await this.workflowRun(runId);
      onUpdate(run);
      if (run.status === "completed") return run;
      if (run.status === "failed") {
        throw new Error(run.error || "The AI workflow failed.");
      }
      await new Promise((resolve) => window.setTimeout(resolve, 700));
    }
    throw new Error("The workflow exceeded 15 minutes and was stopped in the UI.");
  },
  save(dashboardId: number, dashboard: Dashboard) {
    return request<{ dashboard_id: number; dashboard: Dashboard }>("/modify_dashboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dashboard_id: dashboardId, dashboard }),
    });
  },
  modify(dashboardId: number, instruction: string) {
    return request<{ dashboard_id: number; dashboard: Dashboard }>("/modify_dashboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dashboard_id: dashboardId, instruction }),
    });
  },
  chat(dashboardId: number, message: string) {
    return request<{ dashboard_id: number; message: string; dashboard: Dashboard }>(`/dashboards/${dashboardId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  },
  messages(dashboardId: number) {
    return request<{ messages: ChatMessage[] }>(`/dashboards/${dashboardId}/messages`);
  },
  downloadUrl(dashboardId: number) {
    return `${API_URL}/dashboards/${dashboardId}/download`;
  },
  query(datasetId: number, query: Dashboard["components"][number]["query"], filters: Record<string, string> = {}) {
    const params = new URLSearchParams({
      dataset_id: String(datasetId),
      table_id: query.table_id || "main",
      metric: query.metric,
      aggregation: query.aggregation,
      sort: query.sort,
      limit: String(query.limit),
    });
    if (query.group_by) params.set("group_by", query.group_by);
    Object.entries(filters).filter(([, value]) => value).forEach(([qualifiedField, value]) => {
      const [tableId, ...fieldParts] = qualifiedField.split(".");
      if (tableId !== (query.table_id || "main")) return;
      params.append("filter_field", fieldParts.join("."));
      params.append("filter_value", value);
    });
    return request<ChartData>(`/query?${params}`);
  },
  filterOptions(datasetId: number, tableId: string, field: string) {
    const params = new URLSearchParams({ dataset_id: String(datasetId), table_id: tableId, field });
    return request<{ options: string[] }>(`/filter_options?${params}`);
  },
};
