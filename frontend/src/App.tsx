import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3, ChevronDown, CircleHelp, Database, FileSpreadsheet, Filter,
  LayoutDashboard, LoaderCircle, MessageSquareText, PanelRightClose, Plus,
  Save, Settings2, Sparkles, UploadCloud, WandSparkles, X,
} from "lucide-react";
import { ChartCard } from "./components/ChartCard";
import { api } from "./lib/api";
import type { ChartType, Dashboard, DashboardComponent, Dataset } from "./types";

const chartTypes: ChartType[] = ["bar", "line", "area", "pie", "kpi"];
const colors = ["#2563EB", "#7C3AED", "#0F766E", "#E11D48", "#EA580C"];

function App() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [dashboardId, setDashboardId] = useState<number | null>(null);
  const [request, setRequest] = useState("Create an executive overview of workforce composition, service years, and department performance.");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState<"upload" | "generate" | "save" | "modify" | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"build" | "insights">("build");
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [activeFilters, setActiveFilters] = useState<Record<string, string>>({});

  const selected = useMemo(
    () => dashboard?.components.find((component) => component.id === selectedId) || null,
    [dashboard, selectedId],
  );

  useEffect(() => {
    if (!dashboard) return;
    Promise.all(
      dashboard.filters.map(async (filter) => [
        filter.field,
        (await api.filterOptions(dashboard.dataset_id, filter.field)).options,
      ] as const),
    ).then((entries) => setFilterOptions(Object.fromEntries(entries))).catch(() => setFilterOptions({}));
  }, [dashboard?.dataset_id, dashboard?.filters]);

  async function upload(file: File) {
    setLoading("upload");
    setError("");
    try {
      const result = await api.upload(file);
      setDataset(result);
      setDashboard(null);
      setDashboardId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setLoading(null);
    }
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) await upload(file);
  }

  async function generate() {
    if (!dataset) return;
    setLoading("generate");
    setError("");
    try {
      const result = await api.generate(dataset.id, request);
      setDashboard(result.dashboard);
      setDashboardId(result.dashboard_id);
      setSelectedId(result.dashboard.components[0]?.id || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed.");
    } finally {
      setLoading(null);
    }
  }

  function updateComponent(patch: Partial<DashboardComponent>) {
    if (!dashboard || !selectedId) return;
    setDashboard({
      ...dashboard,
      components: dashboard.components.map((component) =>
        component.id === selectedId ? { ...component, ...patch } : component,
      ),
    });
  }

  async function save() {
    if (!dashboard || !dashboardId) return;
    setLoading("save");
    try {
      const result = await api.save(dashboardId, dashboard);
      setDashboard(result.dashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setLoading(null);
    }
  }

  async function refine() {
    if (!dashboardId || !instruction.trim()) return;
    setLoading("modify");
    try {
      const result = await api.modify(dashboardId, instruction);
      setDashboard(result.dashboard);
      setInstruction("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refinement failed.");
    } finally {
      setLoading(null);
    }
  }

  const background = dashboard?.theme.background || "#F4F7FB";
  const surface = dashboard?.theme.surface || "#FFFFFF";
  const primary = dashboard?.theme.primary || "#2563EB";
  const accent = dashboard?.theme.accent || "#14B8A6";

  return (
    <div className="min-h-screen bg-[#f6f8fb] text-slate-800">
      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center border-b border-slate-200 bg-white px-5">
        <div className="flex w-72 items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-200">
            <BarChart3 size={19} strokeWidth={2.5} />
          </div>
          <div>
            <p className="text-[17px] font-bold leading-none tracking-tight text-slate-900">Text2BI</p>
            <p className="mt-1 text-[10px] font-medium uppercase tracking-[.16em] text-slate-400">AI analytics studio</p>
          </div>
        </div>
        <nav className="flex flex-1 items-center gap-1">
          <button className="nav-button nav-button-active"><LayoutDashboard size={16} /> Studio</button>
          <button className="nav-button"><Database size={16} /> Datasets</button>
        </nav>
        <div className="flex items-center gap-2">
          <span className="hidden rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 sm:block">Agents ready</span>
          <button className="icon-button" aria-label="Help"><CircleHelp size={18} /></button>
          <button className="icon-button" aria-label="Settings"><Settings2 size={18} /></button>
          <div className="ml-1 grid h-8 w-8 place-items-center rounded-full bg-slate-900 text-xs font-semibold text-white">CM</div>
        </div>
      </header>

      <aside className="fixed bottom-0 left-0 top-16 z-30 w-72 overflow-y-auto border-r border-slate-200 bg-white p-4">
        <div className="mb-5 flex items-center justify-between px-1">
          <div>
            <p className="text-sm font-semibold text-slate-900">New analysis</p>
            <p className="mt-0.5 text-xs text-slate-400">Data to decisions in minutes</p>
          </div>
          <button className="icon-button"><Plus size={17} /></button>
        </div>

        <section className="side-card">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-slate-700">
            <span className="step">1</span> Connect data
          </div>
          <button
            onClick={() => fileInput.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              const file = event.dataTransfer.files[0];
              if (file) void upload(file);
            }}
            className="w-full rounded-xl border border-dashed border-slate-300 bg-slate-50/70 px-3 py-5 text-center transition hover:border-blue-400 hover:bg-blue-50/40"
          >
            {loading === "upload" ? (
              <LoaderCircle className="mx-auto animate-spin text-blue-600" size={24} />
            ) : dataset ? (
              <>
                <FileSpreadsheet className="mx-auto text-emerald-600" size={25} />
                <p className="mt-2 truncate text-xs font-semibold text-slate-700">{dataset.name}</p>
                <p className="mt-1 text-[11px] text-slate-400">{dataset.row_count.toLocaleString()} rows · {dataset.column_count} columns</p>
              </>
            ) : (
              <>
                <UploadCloud className="mx-auto text-slate-400" size={25} />
                <p className="mt-2 text-xs font-semibold text-slate-700">Drop CSV or Excel</p>
                <p className="mt-1 text-[11px] text-slate-400">or click to browse · 25 MB max</p>
              </>
            )}
          </button>
          <input ref={fileInput} onChange={onFile} className="hidden" type="file" accept=".csv,.xlsx,.xls" />
        </section>

        <section className="side-card mt-3">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-slate-700">
            <span className="step">2</span> Describe your goal
          </div>
          <textarea
            value={request}
            onChange={(event) => setRequest(event.target.value)}
            rows={5}
            className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:ring-2 focus:ring-blue-100"
            placeholder="e.g. Show revenue trends and identify underperforming regions..."
          />
          <button onClick={generate} disabled={!dataset || loading !== null} className="primary-button mt-3 w-full">
            {loading === "generate" ? <LoaderCircle className="animate-spin" size={15} /> : <WandSparkles size={15} />}
            Generate dashboard
          </button>
          {!dataset && <p className="mt-2 text-center text-[10px] text-slate-400">Upload a dataset to continue</p>}
        </section>

        {dataset && (
          <section className="mt-4 border-t border-slate-100 pt-4">
            <p className="px-1 text-[10px] font-bold uppercase tracking-[.14em] text-slate-400">Detected schema</p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {[
                [dataset.profile.metrics.length, "Metrics"],
                [dataset.profile.dimensions.length, "Dimensions"],
                [dataset.profile.dates.length, "Dates"],
              ].map(([value, label]) => (
                <div key={String(label)} className="rounded-lg bg-slate-50 p-2 text-center">
                  <p className="text-sm font-bold text-slate-700">{value}</p>
                  <p className="text-[9px] text-slate-400">{label}</p>
                </div>
              ))}
            </div>
          </section>
        )}
      </aside>

      <main className="ml-72 min-h-screen pt-16" style={{ marginRight: dashboard ? 304 : 0 }}>
        {!dashboard ? (
          <EmptyState hasDataset={Boolean(dataset)} />
        ) : (
          <div className="min-h-[calc(100vh-4rem)]" style={{ background }}>
            <div className="sticky top-16 z-20 flex h-14 items-center justify-between border-b border-slate-200/80 bg-white/90 px-6 backdrop-blur">
              <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1">
                <button onClick={() => setActiveTab("build")} className={`tab ${activeTab === "build" ? "tab-active" : ""}`}>Dashboard</button>
                <button onClick={() => setActiveTab("insights")} className={`tab ${activeTab === "insights" ? "tab-active" : ""}`}>AI insights</button>
              </div>
              <div className="flex items-center gap-2">
                <span className="hidden text-[11px] text-slate-400 xl:block">Quality score <b className="text-emerald-600">{dashboard.quality_score}/100</b></span>
                <button onClick={save} className="secondary-button">
                  {loading === "save" ? <LoaderCircle className="animate-spin" size={14} /> : <Save size={14} />} Save
                </button>
              </div>
            </div>

            {activeTab === "build" ? (
              <div className="mx-auto max-w-[1400px] p-6">
                <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold text-blue-600">
                      <Sparkles size={13} /> AI-GENERATED REPORT
                    </div>
                    <input
                      value={dashboard.title}
                      onChange={(event) => setDashboard({ ...dashboard, title: event.target.value })}
                      className="w-full bg-transparent text-2xl font-bold tracking-tight text-slate-900 outline-none"
                    />
                    <p className="mt-1 text-xs text-slate-500">{dashboard.description}</p>
                  </div>
                  <div className="flex gap-2">
                    {dashboard.filters.map((filter) => (
                      <label key={filter.id} className="filter-button">
                        <Filter size={13} />
                        <select
                          value={activeFilters[filter.field] || ""}
                          onChange={(event) => setActiveFilters({ ...activeFilters, [filter.field]: event.target.value })}
                          className="max-w-32 bg-transparent outline-none"
                          aria-label={`Filter by ${filter.label}`}
                        >
                          <option value="">{filter.label}: All</option>
                          {(filterOptions[filter.field] || []).map((option) => <option key={option} value={option}>{option}</option>)}
                        </select>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-12 gap-4">
                  {dashboard.components.map((component) => (
                    <ChartCard
                      key={component.id}
                      component={component}
                      datasetId={dashboard.dataset_id}
                      primary={primary}
                      accent={accent}
                      selected={selectedId === component.id}
                      onSelect={() => setSelectedId(component.id)}
                      filters={activeFilters}
                    />
                  ))}
                </div>
              </div>
            ) : (
              <Insights dashboard={dashboard} primary={primary} surface={surface} />
            )}
          </div>
        )}
      </main>

      {dashboard && (
        <aside className="fixed bottom-0 right-0 top-16 z-30 w-[304px] overflow-y-auto border-l border-slate-200 bg-white">
          <div className="flex h-14 items-center justify-between border-b border-slate-100 px-5">
            <p className="text-sm font-semibold text-slate-900">Properties</p>
            <button className="icon-button" aria-label="Close properties"><PanelRightClose size={17} /></button>
          </div>
          <div className="p-5">
            {selected ? (
              <>
                <label className="label">Component title</label>
                <input value={selected.title} onChange={(e) => updateComponent({ title: e.target.value })} className="field" />
                <label className="label mt-5">Visualization</label>
                <div className="grid grid-cols-3 gap-2">
                  {chartTypes.map((type) => (
                    <button key={type} onClick={() => updateComponent({ type })} className={`chart-type ${selected.type === type ? "chart-type-active" : ""}`}>
                      <BarChart3 size={15} /> {type}
                    </button>
                  ))}
                </div>
                <label className="label mt-5">Metric</label>
                <div className="field flex items-center justify-between"><span className="truncate">{selected.query.metric}</span><ChevronDown size={14} /></div>
                <label className="label mt-5">Aggregation</label>
                <select
                  value={selected.query.aggregation}
                  onChange={(e) => updateComponent({ query: { ...selected.query, aggregation: e.target.value as DashboardComponent["query"]["aggregation"] } })}
                  className="field"
                >
                  {["sum", "avg", "count", "min", "max", "distinct_count"].map((value) => <option key={value}>{value}</option>)}
                </select>
                <button
                  onClick={() => setDashboard({ ...dashboard, components: dashboard.components.filter((c) => c.id !== selected.id) })}
                  className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-rose-200 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50"
                >
                  <X size={14} /> Remove component
                </button>
              </>
            ) : <p className="text-xs text-slate-400">Select a dashboard component to edit it.</p>}

            <div className="my-6 border-t border-slate-100" />
            <label className="label">Theme color</label>
            <div className="mt-2 flex gap-2">
              {colors.map((color) => (
                <button
                  key={color}
                  onClick={() => setDashboard({ ...dashboard, theme: { ...dashboard.theme, primary: color } })}
                  style={{ backgroundColor: color }}
                  className={`h-7 w-7 rounded-full border-2 border-white shadow ${primary === color ? "ring-2 ring-slate-400" : ""}`}
                  aria-label={`Use ${color}`}
                />
              ))}
            </div>

            <div className="my-6 border-t border-slate-100" />
            <div className="mb-2 flex items-center gap-2">
              <Sparkles size={14} className="text-blue-600" />
              <p className="text-xs font-semibold text-slate-800">Refine with AI</p>
            </div>
            <textarea
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              rows={3}
              className="field resize-none"
              placeholder='Try “use a dark theme” or “make the layout compact”'
            />
            <button onClick={refine} disabled={!instruction.trim() || loading !== null} className="secondary-button mt-2 w-full justify-center">
              {loading === "modify" ? <LoaderCircle className="animate-spin" size={14} /> : <MessageSquareText size={14} />} Apply refinement
            </button>
          </div>
        </aside>
      )}

      {error && (
        <div className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-slate-900 px-4 py-3 text-xs text-white shadow-xl">
          {error}<button onClick={() => setError("")}><X size={14} /></button>
        </div>
      )}
    </div>
  );
}

function EmptyState({ hasDataset }: { hasDataset: boolean }) {
  return (
    <div className="grid min-h-[calc(100vh-4rem)] place-items-center px-8">
      <div className="max-w-lg text-center">
        <div className="relative mx-auto mb-7 h-28 w-40">
          <div className="absolute left-4 top-7 h-20 w-28 rotate-[-7deg] rounded-2xl border border-slate-200 bg-white shadow-panel" />
          <div className="absolute right-3 top-1 h-24 w-32 rotate-[5deg] rounded-2xl border border-blue-100 bg-gradient-to-br from-white to-blue-50 p-4 shadow-panel">
            <div className="mb-3 flex h-3 items-end gap-1">
              {[4, 8, 12, 7, 15].map((height, index) => <i key={index} className="w-2 rounded-sm bg-blue-500" style={{ height }} />)}
            </div>
            <div className="h-2 w-20 rounded bg-slate-200" />
            <div className="mt-2 h-2 w-14 rounded bg-slate-100" />
          </div>
          <div className="absolute bottom-0 left-1/2 grid h-11 w-11 -translate-x-1/2 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-200">
            <Sparkles size={20} />
          </div>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{hasDataset ? "Your data is ready" : "Turn questions into dashboards"}</h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-slate-500">
          {hasDataset ? "Describe the business view you need, then let the analyst agents profile, plan, design, and review it." : "Upload a CSV or Excel file. Text2BI discovers the schema and builds an editable, interactive report from plain English."}
        </p>
        <div className="mt-7 flex justify-center gap-7 text-[11px] font-medium text-slate-400">
          <span>01 · Profile</span><span>02 · Analyze</span><span>03 · Design</span><span>04 · Review</span>
        </div>
      </div>
    </div>
  );
}

function Insights({ dashboard, primary, surface }: { dashboard: Dashboard; primary: string; surface: string }) {
  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="mb-7">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold" style={{ color: primary }}><Sparkles size={15} /> AI ANALYSIS</div>
        <h2 className="text-2xl font-bold text-slate-900">What deserves your attention</h2>
        <p className="mt-2 text-sm text-slate-500">Decision-ready observations generated from the dashboard structure and business objective.</p>
      </div>
      <div className="space-y-3">
        {dashboard.insights.map((insight, index) => (
          <div key={insight} className="flex gap-4 rounded-2xl border border-slate-200 p-5 shadow-panel" style={{ background: surface }}>
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-xs font-bold text-white" style={{ background: primary }}>{index + 1}</span>
            <div>
              <p className="text-sm font-semibold text-slate-800">{insight}</p>
              <p className="mt-1 text-xs leading-5 text-slate-400">Review the relevant visualization and validate this observation with the metric owner.</p>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-7 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
        <p className="text-sm font-semibold text-emerald-900">Critic review · {dashboard.quality_score}/100</p>
        {dashboard.critic_notes.map((note) => <p key={note} className="mt-2 text-xs text-emerald-700">• {note}</p>)}
      </div>
    </div>
  );
}

export default App;
