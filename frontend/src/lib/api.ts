import type { ChartData, Dashboard, Dataset } from "../types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Something went wrong." }));
    throw new Error(body.detail || "Request failed.");
  }
  return response.json();
}

export const api = {
  upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<Dataset>("/upload_dataset", { method: "POST", body });
  },
  generate(datasetId: number, businessRequest: string) {
    return request<{ dashboard_id: number; dashboard: Dashboard }>("/generate_dashboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId, business_request: businessRequest }),
    });
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
  query(datasetId: number, query: Dashboard["components"][number]["query"], filters: Record<string, string> = {}) {
    const params = new URLSearchParams({
      dataset_id: String(datasetId),
      metric: query.metric,
      aggregation: query.aggregation,
      sort: query.sort,
      limit: String(query.limit),
    });
    if (query.group_by) params.set("group_by", query.group_by);
    const activeFilter = Object.entries(filters).find(([, value]) => value);
    if (activeFilter) {
      params.set("filter_field", activeFilter[0]);
      params.set("filter_value", activeFilter[1]);
    }
    return request<ChartData>(`/query?${params}`);
  },
  filterOptions(datasetId: number, field: string) {
    const params = new URLSearchParams({ dataset_id: String(datasetId), field });
    return request<{ options: string[] }>(`/filter_options?${params}`);
  },
};
