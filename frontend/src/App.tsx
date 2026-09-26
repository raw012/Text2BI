import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  ArrowRight,
  Bot,
  Check,
  ChevronRight,
  Database,
  Download,
  FileSpreadsheet,
  House,
  Image,
  LayoutDashboard,
  LoaderCircle,
  MessageSquareText,
  Plus,
  Search,
  RefreshCw,
  RotateCcw,
  Send,
  Sparkles,
  Table2,
  UploadCloud,
  X,
} from "lucide-react";
import { ChartCard } from "./components/ChartCard";
import { api } from "./lib/api";
import type { ChatMessage, Dashboard, DashboardSummary, Dataset, DatasetPreview, WorkflowRun } from "./types";

const workflowSteps = [
  { node: "brand_identity", label: "Brand" },
  { node: "data_analyst", label: "Data" },
  { node: "business_analyst", label: "Business" },
  { node: "kpi_calculator", label: "KPI" },
  { node: "bi_designer", label: "Design" },
  { node: "render_preview", label: "Render" },
  { node: "bi_evaluator", label: "Evaluate" },
  { node: "published", label: "Publish" },
];

function AnalysisStudio() {
  const fileInput = useRef<HTMLInputElement>(null);
  const logoInput = useRef<HTMLInputElement>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [availableDatasets, setAvailableDatasets] = useState<Dataset[]>([]);
  const [dataMode, setDataMode] = useState<"existing" | "upload" | "database" | "curated">("existing");
  const [curatedTable, setCuratedTable] = useState<"tlc_daily" | "tlc_pickup_zone">("tlc_daily");
  const [databaseUrl, setDatabaseUrl] = useState("");
  const [databaseTable, setDatabaseTable] = useState("");
  const [databaseName, setDatabaseName] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [dashboardId, setDashboardId] = useState<number | null>(null);
  const [request, setRequest] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [logoName, setLogoName] = useState("");
  const [loading, setLoading] = useState<"upload" | "connect" | "generate" | "modify" | null>(null);
  const [workflowRun, setWorkflowRun] = useState<WorkflowRun | null>(null);
  const [instruction, setInstruction] = useState("");
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [activeFilters, setActiveFilters] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    api.datasets().then(setAvailableDatasets).catch(() => setAvailableDatasets([]));
    const id = Number(new URLSearchParams(window.location.search).get("dashboard"));
    if (!Number.isInteger(id) || id < 1) return;
    api.dashboard(id)
      .then((result) => {
        setDashboard(result.dashboard);
        setDashboardId(result.dashboard_id);
      })
      .catch(() => window.history.replaceState({}, "", window.location.pathname));
  }, []);

  useEffect(() => {
    if (!dashboard) return;
    Promise.all(
      dashboard.filters.map(async (filter) => {
        const key = `${filter.table_id}.${filter.field}`;
        const result = await api.filterOptions(
          dashboard.dataset_id,
          filter.table_id,
          filter.field,
        );
        return [key, result.options] as const;
      }),
    )
      .then((entries) => setFilterOptions(Object.fromEntries(entries)))
      .catch(() => setFilterOptions({}));
  }, [dashboard]);

  const kpis = useMemo(
    () => dashboard?.components.filter((component) => component.type === "kpi") || [],
    [dashboard],
  );
  const charts = useMemo(
    () => dashboard?.components.filter((component) => component.type !== "kpi") || [],
    [dashboard],
  );

  async function upload(files: File[]) {
    if (!files.length) return;
    setLoading("upload");
    setError("");
    try {
      const uploaded = await api.upload(files);
      setDataset(uploaded);
      setAvailableDatasets(await api.datasets());
      setDashboard(null);
      setDashboardId(null);
      setWorkflowRun(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setLoading(null);
    }
  }

  async function onFiles(event: ChangeEvent<HTMLInputElement>) {
    await upload(Array.from(event.target.files || []));
  }

  async function importDatabase() {
    if (!databaseUrl.trim() || !databaseTable.trim()) return;
    setLoading("connect");
    setError("");
    try {
      const imported = await api.connectDatabase({
        database_url: databaseUrl.trim(),
        table_name: databaseTable.trim(),
        dataset_name: databaseName.trim() || undefined,
      });
      setDataset(imported);
      setAvailableDatasets(await api.datasets());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Database import failed.");
    } finally {
      setLoading(null);
    }
  }

  async function importCuratedTlc() {
    setLoading("connect");
    setError("");
    try {
      const imported = await api.connectCuratedTlc(curatedTable);
      setDataset(imported);
      setAvailableDatasets(await api.datasets());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Curated TLC import failed.");
    } finally {
      setLoading(null);
    }
  }

  async function onLogo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const uploaded = await api.uploadLogo(file);
      setLogoUrl(uploaded.logo_url);
      setLogoName(file.name);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Logo upload failed.");
    }
  }

  async function generate() {
    if (!dataset || !request.trim()) return;
    setLoading("generate");
    setError("");
    setWorkflowRun(null);
    try {
      const started = await api.startGenerate(dataset.id, request, logoUrl);
      const result = await api.waitForRun(started.run_id, setWorkflowRun);
      if (!result.result?.dashboard || !result.result.dashboard_id) {
        throw new Error("The workflow finished without a dashboard result.");
      }
      setDashboard(result.result.dashboard);
      setDashboardId(result.result.dashboard_id);
      setMessages([]);
      window.history.replaceState({}, "", `?dashboard=${result.result.dashboard_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Generation failed.");
    } finally {
      setLoading(null);
    }
  }

  async function refine() {
    if (!dashboardId || !instruction.trim()) return;
    const message = instruction.trim();
    setLoading("modify");
    setError("");
    setWorkflowRun(null);
    setMessages((current) => [...current, { role: "user", content: message }]);
    try {
      const started = await api.startRefinement(dashboardId, message);
      const result = await api.waitForRun(started.run_id, setWorkflowRun);
      if (!result.result?.dashboard) {
        throw new Error("The revision finished without a dashboard result.");
      }
      setDashboard(result.result.dashboard);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: result.result?.message || "The evaluated revision is ready.",
        },
      ]);
      setInstruction("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Refinement failed.");
    } finally {
      setLoading(null);
    }
  }

  function newAnalysis() {
    setDashboard(null);
    setDashboardId(null);
    setWorkflowRun(null);
    setMessages([]);
    setActiveFilters({});
    window.history.replaceState({}, "", window.location.pathname);
  }

  if (!dashboard) {
    return (
      <div className="product-shell">
        <AppHeader />
        <main className="builder-page">
          <section className="builder-copy">
            <p className="eyebrow">AI BUSINESS INTELLIGENCE</p>
            <h1>Turn your data into an executive dashboard.</h1>
            <p>
              Upload your files and describe the decisions the report should support.
              Text2BI profiles the data, defines KPIs, designs the report, and evaluates
              the result.
            </p>
          </section>

          <div className="builder-grid">
            <section className="builder-card">
              <div className="card-heading">
                <span>01</span>
                <div>
                  <h2>Connect data</h2>
                  <p>Reuse a source, upload files, or import a database table.</p>
                </div>
              </div>
              <div className="data-mode-tabs">
                <button className={dataMode === "existing" ? "active" : ""} onClick={() => setDataMode("existing")}><Database size={14} /> Existing</button>
                <button className={dataMode === "upload" ? "active" : ""} onClick={() => setDataMode("upload")}><UploadCloud size={14} /> Upload</button>
                <button className={dataMode === "database" ? "active" : ""} onClick={() => setDataMode("database")}><Table2 size={14} /> Database</button>
                <button className={dataMode === "curated" ? "active" : ""} onClick={() => setDataMode("curated")}><Table2 size={14} /> Curated TLC</button>
              </div>
              {dataMode === "existing" && (
                <div className="existing-source-picker">
                  {availableDatasets.map((item) => <button key={item.id} className={dataset?.id === item.id ? "selected" : ""} onClick={() => setDataset(item)}><span><FileSpreadsheet size={16} /></span><div><strong>{item.name}</strong><small>{item.row_count.toLocaleString()} rows · {item.column_count} fields</small></div>{dataset?.id === item.id && <Check size={15} />}</button>)}
                  {!availableDatasets.length && <div className="source-picker-empty">No saved sources yet. Upload a file or connect a database.</div>}
                </div>
              )}
              {dataMode === "upload" && <button
                  className={`upload-zone ${dataset ? "has-file" : ""}`}
                  onClick={() => fileInput.current?.click()}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => { event.preventDefault(); void upload(Array.from(event.dataTransfer.files)); }}
                  disabled={loading !== null}
                >
                  {loading === "upload" ? <LoaderCircle className="spin" size={28} /> : dataset ? <><FileSpreadsheet size={28} /><strong>{dataset.name}</strong><small>{dataset.profile.tables.length} tables · {dataset.row_count.toLocaleString()} rows · {dataset.column_count} fields</small></> : <><UploadCloud size={30} /><strong>Drop files here or browse</strong><small>Same-name uploads become a new source version</small></>}
                </button>}
              {dataMode === "database" && <div className="database-connect-form">
                <label><span>Connection URL</span><input type="password" value={databaseUrl} onChange={(event) => setDatabaseUrl(event.target.value)} placeholder="postgresql+psycopg://user:password@host/database" /></label>
                <div><label><span>Table</span><input value={databaseTable} onChange={(event) => setDatabaseTable(event.target.value)} placeholder="employees" /></label><label><span>Display name</span><input value={databaseName} onChange={(event) => setDatabaseName(event.target.value)} placeholder="HR warehouse" /></label></div>
                <button onClick={() => void importDatabase()} disabled={!databaseUrl.trim() || !databaseTable.trim() || loading !== null}>{loading === "connect" ? <LoaderCircle className="spin" size={15} /> : <Database size={15} />} Import table snapshot</button>
                <small>Credentials are used for this import and are not stored by Text2BI.</small>
              </div>}
              {dataMode === "curated" && <div className="database-connect-form">
                <label><span>Serving table</span><select value={curatedTable} onChange={(event) => setCuratedTable(event.target.value as "tlc_daily" | "tlc_pickup_zone")}><option value="tlc_daily">Daily trips</option><option value="tlc_pickup_zone">Pickup zones</option></select></label>
                <button onClick={() => void importCuratedTlc()} disabled={loading !== null}>{loading === "connect" ? <LoaderCircle className="spin" size={15} /> : <Database size={15} />} Use curated table</button>
                <small>Uses the application PostgreSQL connection. Run the Spark pipeline first.</small>
              </div>}
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.xlsx,.xls"
                multiple
                hidden
                onChange={onFiles}
              />

              <button
                className="logo-upload"
                onClick={() => logoInput.current?.click()}
                disabled={loading !== null}
              >
                <Image size={16} />
                <span>{logoName || "Optional: upload a company logo"}</span>
                <ArrowRight size={15} />
              </button>
              <input
                ref={logoInput}
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.svg"
                hidden
                onChange={onLogo}
              />
              <p className="logo-note">
                If omitted, Text2BI will look for the company identity named in your request
                and otherwise create a clearly marked custom brand mark.
              </p>
            </section>

            <section className="builder-card">
              <div className="card-heading">
                <span>02</span>
                <div>
                  <h2>Describe the decision view</h2>
                  <p>Focus on audience, goals, and required KPIs.</p>
                </div>
              </div>
              <textarea
                className="goal-input"
                value={request}
                onChange={(event) => setRequest(event.target.value)}
                disabled={loading !== null}
                placeholder={"Company: Mercedes-Benz\nCreate an executive HR dashboard showing headcount, average age, tenure, department composition, and employee status."}
              />
              <button
                className="generate-button"
                onClick={generate}
                disabled={!dataset || !request.trim() || loading !== null}
              >
                {loading === "generate" ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <Sparkles size={18} />
                )}
                {loading === "generate" ? "Building dashboard" : "Generate dashboard"}
              </button>
            </section>
          </div>

          {loading === "generate" && workflowRun && (
            <WorkflowProgress run={workflowRun} />
          )}
        </main>
        <ErrorToast error={error} onClose={() => setError("")} />
      </div>
    );
  }

  const primary = dashboard.theme.primary || "#111827";
  const accent = dashboard.theme.accent || "#00ADEF";
  return (
    <div
      className="product-shell report-mode"
      style={{
        "--brand-primary": primary,
        "--brand-accent": accent,
      } as CSSProperties}
    >
      <AppHeader
        status={loading ? "Agents working" : dashboard.workflow_status.replace(/_/g, " ")}
      >
        <button className="header-action" onClick={newAnalysis}>
          <RefreshCw size={15} /> New analysis
        </button>
        {dashboardId && (
          <a className="header-action primary-action" href={api.downloadUrl(dashboardId)} download>
            <Download size={15} /> Download HTML
          </a>
        )}
      </AppHeader>

      {loading === "modify" && workflowRun && (
        <div className="refinement-progress">
          <WorkflowProgress run={workflowRun} compact />
        </div>
      )}

      <main className="report-page">
        <header className="report-titlebar">
          <div className="company-lockup">
            {dashboard.logo_url ? (
              <img src={dashboard.logo_url} alt={`${dashboard.company_name || "Company"} logo`} />
            ) : (
              <div className="brand-fallback">
                {(dashboard.company_name || dashboard.title).slice(0, 2).toUpperCase()}
              </div>
            )}
            <div>
              <p>{dashboard.company_name || "Executive intelligence"}</p>
              <h1>{dashboard.title}</h1>
              <span>{dashboard.description}</span>
            </div>
          </div>
          <div className="evaluation-summary">
            <span className={dashboard.workflow_status === "passed" ? "passed" : "review"}>
              {dashboard.workflow_status === "passed" ? <Check size={14} /> : <RotateCcw size={14} />}
              {dashboard.workflow_status.replace(/_/g, " ")}
            </span>
            <b>{dashboard.quality_score}/100</b>
            <small>BI evaluation</small>
          </div>
        </header>

        {dashboard.filters.length > 0 && (
          <section className="filter-strip" aria-label="Dashboard filters">
            <strong>Filter report</strong>
            {dashboard.filters.map((filter) => {
              const key = `${filter.table_id}.${filter.field}`;
              return (
                <label key={filter.id}>
                  <span>{filter.label}</span>
                  <select
                    value={activeFilters[key] || ""}
                    onChange={(event) =>
                      setActiveFilters({ ...activeFilters, [key]: event.target.value })
                    }
                  >
                    <option value="">All</option>
                    {(filterOptions[key] || []).map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
              );
            })}
            <button onClick={() => setActiveFilters({})}>Reset</button>
          </section>
        )}

        <section className="dashboard-section">
          <div className="section-intro">
            <div>
              <p>EXECUTIVE OVERVIEW</p>
              <h2>Key performance at a glance</h2>
            </div>
            <span>Validated from {dataset?.profile.tables.length || 1} source table(s)</span>
          </div>

          <div className="kpi-grid">
            {kpis.map((component) => (
              <ChartCard
                key={component.id}
                component={component}
                datasetId={dashboard.dataset_id}
                primary={primary}
                accent={accent}
                filters={activeFilters}
              />
            ))}
          </div>

          <div className="report-grid">
            {charts.map((component) => (
              <ChartCard
                key={component.id}
                component={component}
                datasetId={dashboard.dataset_id}
                primary={primary}
                accent={accent}
                filters={activeFilters}
              />
            ))}
          </div>
        </section>

        <section className="result-footer">
          <div className="insight-panel">
            <p className="eyebrow">EVIDENCE-BACKED INSIGHTS</p>
            <div className="insight-list">
              {dashboard.insights.slice(0, 4).map((insight) => (
                <article key={`${insight.component_id}-${insight.text}`}>
                  <span />
                  <p>{insight.text}</p>
                </article>
              ))}
            </div>
          </div>

        </section>
      </main>
      <button className="copilot-launch" onClick={() => setCopilotOpen(true)} aria-label="Open dashboard copilot">
        <span><Sparkles size={17} /></span>
        <div><strong>Dashboard Copilot</strong><small>Change this report with AI</small></div>
        <MessageSquareText size={17} />
      </button>
      {copilotOpen && (
        <aside className="copilot-drawer" aria-label="Dashboard Copilot">
          <header>
            <div><span><Sparkles size={17} /></span><div><strong>Dashboard Copilot</strong><small>Edits the current dashboard only</small></div></div>
            <button onClick={() => setCopilotOpen(false)} aria-label="Close copilot"><X size={17} /></button>
          </header>
          <div className="copilot-context">
            <span>Current report</span>
            <strong>{dashboard.title}</strong>
            <small>{dashboard.components.length} visuals · revision {dashboard.revision}</small>
          </div>
          <div className="copilot-quick-actions">
            <p>Suggested changes</p>
            {["Add a headcount trend chart", "Make department comparison more prominent", "Add an Entity filter", "Summarize the three most important insights"].map((prompt) => (
              <button key={prompt} onClick={() => setInstruction(prompt)}>{prompt}<ArrowRight size={13} /></button>
            ))}
          </div>
          <div className="copilot-conversation">
            {!messages.length && <div className="copilot-empty"><MessageSquareText size={22} /><p>Describe a change. Copilot will update the dashboard, validate it, and preserve the underlying data.</p></div>}
            {messages.map((message, index) => (
              <article className={message.role} key={`${message.role}-${index}`}><span>{message.role === "assistant" ? "Copilot" : "You"}</span><p>{message.content}</p></article>
            ))}
          </div>
          <footer>
            <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} disabled={loading !== null} placeholder="Describe a chart, KPI, filter, or layout change…" />
            <button onClick={refine} disabled={!instruction.trim() || loading !== null}>
              {loading === "modify" ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}
            </button>
            <small>Changes create a new evaluated dashboard revision.</small>
          </footer>
        </aside>
      )}
      <ErrorToast error={error} onClose={() => setError("")} />
    </div>
  );
}

function AppHeader({
  status,
  children,
}: {
  status?: string;
  children?: ReactNode;
}) {
  return (
    <header className="app-header">
      <div className="app-brand">
        <div className="app-mark"><Sparkles size={19} /></div>
        <div><strong>Text2BI</strong><span>AI analytics studio</span></div>
      </div>
      <div className="header-tools">
        {status && <span className="run-status"><i />{status}</span>}
        {children}
      </div>
    </header>
  );
}

function WorkflowProgress({ run, compact = false }: { run: WorkflowRun; compact?: boolean }) {
  const activeIndex = Math.max(
    0,
    workflowSteps.findIndex((step) => step.node === run.node),
  );
  return (
    <section className={`workflow-progress ${compact ? "compact" : ""}`}>
      <div className="progress-copy">
        <div>
          <p className="eyebrow">LIVE AGENT WORKFLOW</p>
          <h2>{run.stage}</h2>
          <span>{run.message}</span>
        </div>
        <div className="iteration-count">
          <b>{run.iteration || 1}</b><span>/ {run.max_iterations}</span>
          <small>iteration</small>
        </div>
      </div>
      <div className="progress-track"><i style={{ width: `${run.progress}%` }} /></div>
      <div className="agent-steps">
        {workflowSteps.map((step, index) => {
          const isComplete = run.node === "published" || index < activeIndex;
          const isActive = index === activeIndex && run.node !== "published";
          return (
            <div className={`${isComplete ? "complete" : ""} ${isActive ? "active" : ""}`} key={step.node}>
              <span>{isComplete ? <Check size={12} /> : index + 1}</span>
              <p>{step.label}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ErrorToast({ error, onClose }: { error: string; onClose: () => void }) {
  if (!error) return null;
  return (
    <div className="error-toast">
      <span>{error}</span>
      <button onClick={onClose}><X size={15} /></button>
    </div>
  );
}

type WorkspaceView = "home" | "dashboards" | "data" | "assistant" | "studio";

function App() {
  const [view, setView] = useState<WorkspaceView>(() =>
    new URLSearchParams(window.location.search).has("dashboard") ? "studio" : "home",
  );
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dashboards, setDashboards] = useState<DashboardSummary[]>([]);
  const [workspaceError, setWorkspaceError] = useState("");
  const [loadingLibrary, setLoadingLibrary] = useState(true);
  const [studioKey, setStudioKey] = useState(0);

  async function refreshLibrary() {
    setLoadingLibrary(true);
    try {
      const [dataResult, dashboardResult] = await Promise.all([
        api.datasets(),
        api.dashboards(),
      ]);
      setDatasets(dataResult);
      setDashboards(dashboardResult.dashboards);
    } catch (caught) {
      setWorkspaceError(caught instanceof Error ? caught.message : "Could not load workspace.");
    } finally {
      setLoadingLibrary(false);
    }
  }

  useEffect(() => { void refreshLibrary(); }, []);

  function openDashboard(id: number) {
    window.history.replaceState({}, "", `?dashboard=${id}`);
    setStudioKey((current) => current + 1);
    setView("studio");
  }

  function openStudio() {
    window.history.replaceState({}, "", window.location.pathname);
    setStudioKey((current) => current + 1);
    setView("studio");
  }

  function navigate(next: WorkspaceView) {
    if (next !== "studio") window.history.replaceState({}, "", window.location.pathname);
    setView(next);
    if (next === "home" || next === "dashboards" || next === "data") void refreshLibrary();
  }

  return (
    <div className="workspace-shell">
      <aside className="workspace-sidebar">
        <div className="workspace-brand"><span><Sparkles size={17} /></span><div><strong>Text2BI</strong><small>AI analytics studio</small></div></div>
        <nav aria-label="Workspace navigation">
          <WorkspaceNav icon={<House size={17} />} label="Home" active={view === "home"} onClick={() => navigate("home")} />
          <WorkspaceNav icon={<LayoutDashboard size={17} />} label="Dashboards" count={dashboards.length} active={view === "dashboards" || view === "studio"} onClick={() => navigate("dashboards")} />
          <WorkspaceNav icon={<Database size={17} />} label="Data sources" count={datasets.length} active={view === "data"} onClick={() => navigate("data")} />
          <WorkspaceNav icon={<Bot size={17} />} label="Ask your data" active={view === "assistant"} onClick={() => navigate("assistant")} />
        </nav>
        <div className="sidebar-foot"><span>Local workspace</span><small>Connected to Text2BI API</small></div>
      </aside>
      <main className="workspace-main">
        <header className="workspace-topbar">
          {view === "studio" ? <button className="workspace-breadcrumb" onClick={() => navigate("dashboards")}><ArrowRight size={14} /> Dashboards <ChevronRight size={13} /><strong>{new URLSearchParams(window.location.search).has("dashboard") ? "Report editor" : "New dashboard"}</strong></button> : <div className="workspace-search"><Search size={15} /><span>Search dashboards and data</span></div>}
          <button className="new-dashboard" onClick={openStudio}><Plus size={16} /> New dashboard</button>
        </header>
        {view === "home" && <WorkspaceHome datasets={datasets} dashboards={dashboards} loading={loadingLibrary} onOpenDashboard={openDashboard} onView={setView} onCreate={openStudio} />}
        {view === "dashboards" && <DashboardLibrary dashboards={dashboards} onOpen={openDashboard} onCreate={openStudio} />}
        {view === "data" && <DataLibrary datasets={datasets} onRefresh={refreshLibrary} onCreate={openStudio} />}
        {view === "assistant" && <DataAssistant datasets={datasets} onCreate={openStudio} />}
        {view === "studio" && <AnalysisStudio key={studioKey} />}
      </main>
      <ErrorToast error={workspaceError} onClose={() => setWorkspaceError("")} />
    </div>
  );
}

function WorkspaceNav({ icon, label, count, active, onClick }: { icon: ReactNode; label: string; count?: number; active: boolean; onClick: () => void }) {
  return <button className={active ? "active" : ""} onClick={onClick}>{icon}<span>{label}</span>{count !== undefined && <b>{count}</b>}</button>;
}

function WorkspaceHome({ datasets, dashboards, loading, onOpenDashboard, onView, onCreate }: { datasets: Dataset[]; dashboards: DashboardSummary[]; loading: boolean; onOpenDashboard: (id: number) => void; onView: (view: WorkspaceView) => void; onCreate: () => void }) {
  const totalRows = datasets.reduce((sum, item) => sum + item.row_count, 0);
  return (
    <div className="workspace-page">
      <div className="page-heading"><div><p className="eyebrow">WORKSPACE OVERVIEW</p><h1>Good morning. Your analytics are ready.</h1><span>Keep dashboards connected to living data, not one-off exports.</span></div><button onClick={onCreate}><Sparkles size={16} /> Build with AI</button></div>
      <section className="workspace-stats">
        <article><LayoutDashboard size={17} /><div><strong>{dashboards.length}</strong><span>Dashboards</span></div></article>
        <article><Database size={17} /><div><strong>{datasets.length}</strong><span>Data sources</span></div></article>
        <article><Table2 size={17} /><div><strong>{totalRows.toLocaleString()}</strong><span>Rows available</span></div></article>
        <article><Check size={17} /><div><strong>{dashboards.filter((item) => item.status === "passed").length}</strong><span>Validated reports</span></div></article>
      </section>
      <section className="workspace-section"><header><div><h2>Recent dashboards</h2><p>Reusable reports that stay connected to their data.</p></div><button onClick={() => onView("dashboards")}>View all <ChevronRight size={14} /></button></header>
        <div className="dashboard-library-grid">
          {loading ? <EmptyState text="Loading workspace…" /> : dashboards.slice(0, 4).map((item) => <DashboardTile key={item.id} item={item} onOpen={onOpenDashboard} />)}
          {!loading && dashboards.length === 0 && <EmptyState text="No saved dashboards yet. Build your first one with AI." action="Create dashboard" onAction={onCreate} />}
        </div>
      </section>
      <section className="workspace-section"><header><div><h2>Data sources</h2><p>Upload once, replace safely, and keep every report intact.</p></div><button onClick={() => onView("data")}>Manage data <ChevronRight size={14} /></button></header>
        <div className="source-row-list">{datasets.slice(0, 3).map((item) => <SourceRow key={item.id} dataset={item} />)}{!datasets.length && <EmptyState text="Upload CSV or Excel data to begin." action="Add data" onAction={() => onView("data")} />}</div>
      </section>
    </div>
  );
}

function DashboardLibrary({ dashboards, onOpen, onCreate }: { dashboards: DashboardSummary[]; onOpen: (id: number) => void; onCreate: () => void }) {
  return <div className="workspace-page"><div className="page-heading"><div><p className="eyebrow">DASHBOARD LIBRARY</p><h1>Dashboards</h1><span>Open, refine and export every report your team has created.</span></div><button onClick={onCreate}><Plus size={16} /> New dashboard</button></div><div className="dashboard-library-grid full">{dashboards.map((item) => <DashboardTile key={item.id} item={item} onOpen={onOpen} />)}{!dashboards.length && <EmptyState text="No dashboards have been saved yet." action="Create dashboard" onAction={onCreate} />}</div></div>;
}

function DashboardTile({ item, onOpen }: { item: DashboardSummary; onOpen: (id: number) => void }) {
  return <button className="dashboard-tile" onClick={() => onOpen(item.id)}><div className="dashboard-thumbnail"><LayoutDashboard size={24} /><span>{item.component_count} visuals</span></div><div className="dashboard-tile-copy"><span className={`library-status ${item.status}`}>{item.status.replace(/_/g, " ")}</span><h3>{item.title}</h3><p>{item.business_request}</p><footer><span>{item.filter_count} filters</span><b>{item.quality_score}/100</b></footer></div></button>;
}

function SourceRow({ dataset, selected, onClick }: { dataset: Dataset; selected?: boolean; onClick?: () => void }) {
  return <button className={`source-row ${selected ? "selected" : ""}`} onClick={onClick}><span className="source-icon"><FileSpreadsheet size={18} /></span><div><strong>{dataset.name}</strong><small>{dataset.profile.tables.length} table{dataset.profile.tables.length === 1 ? "" : "s"} · {dataset.row_count.toLocaleString()} rows · {dataset.column_count} fields</small></div><span className="source-health"><i /> Ready</span><ChevronRight size={15} /></button>;
}

function DataLibrary({ datasets, onRefresh, onCreate }: { datasets: Dataset[]; onRefresh: () => Promise<void>; onCreate: () => void }) {
  const uploadInput = useRef<HTMLInputElement>(null);
  const replaceInput = useRef<HTMLInputElement>(null);
  const [selectedId, setSelectedId] = useState<number | null>(datasets[0]?.id || null);
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const selected = datasets.find((item) => item.id === selectedId) || datasets[0];

  useEffect(() => {
    if (!selected) { setPreview(null); return; }
    api.datasetPreview(selected.id).then(setPreview).catch(() => setPreview(null));
  }, [selected?.id]);

  async function addFiles(files: File[]) {
    if (!files.length) return;
    setBusy(true); setMessage("");
    try { const created = await api.upload(files); await onRefresh(); setSelectedId(created.id); setMessage("Data source uploaded and profiled."); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Upload failed."); }
    finally { setBusy(false); }
  }

  async function replaceFiles(files: File[]) {
    if (!selected || !files.length) return;
    setBusy(true); setMessage("");
    try { await api.replaceDataset(selected.id, files); await onRefresh(); setPreview(await api.datasetPreview(selected.id)); setMessage("New version is live. Existing dashboard layouts were preserved."); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Replacement failed."); }
    finally { setBusy(false); }
  }

  return <div className="workspace-page"><div className="page-heading"><div><p className="eyebrow">DATA WORKSPACE</p><h1>Data sources</h1><span>Preview, refresh and safely replace the data behind your dashboards.</span></div><button onClick={() => uploadInput.current?.click()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <UploadCloud size={16} />} Add data</button><input ref={uploadInput} hidden multiple type="file" accept=".csv,.xlsx,.xls" onChange={(event) => void addFiles(Array.from(event.target.files || []))} /></div>
    {message && <div className={`data-message ${message.toLowerCase().includes("fail") || message.toLowerCase().includes("could") ? "error" : ""}`}>{message}</div>}
    <div className="data-workspace"><aside><div className="data-list-heading"><strong>All sources</strong><span>{datasets.length}</span></div>{datasets.map((item) => <SourceRow key={item.id} dataset={item} selected={item.id === selected?.id} onClick={() => setSelectedId(item.id)} />)}{!datasets.length && <EmptyState text="No data sources yet." action="Upload data" onAction={() => uploadInput.current?.click()} />}</aside>
      <section className="data-detail">{selected ? <><header><div><span className="source-icon large"><Database size={21} /></span><div><h2>{selected.name}</h2><p>{selected.row_count.toLocaleString()} rows · {selected.column_count} fields</p></div></div><div><button className="secondary-button" onClick={() => replaceInput.current?.click()} disabled={busy}><RefreshCw size={14} /> Replace data</button><button className="dark-button" onClick={onCreate}><Sparkles size={14} /> Build dashboard</button><input ref={replaceInput} hidden multiple type="file" accept=".csv,.xlsx,.xls" onChange={(event) => void replaceFiles(Array.from(event.target.files || []))} /></div></header><div className="data-tabs"><button className="active">Data preview</button><button>Schema</button><button>Version history</button><button>Connections</button></div>{preview ? <div className="preview-table-wrap"><table><thead><tr>{preview.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{preview.rows.map((row, index) => <tr key={index}>{preview.columns.map((column) => <td key={column}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table><footer>Showing {preview.rows.length} of {preview.total_rows.toLocaleString()} rows</footer></div> : <EmptyState text="Select a data source to preview its rows." />}</> : <EmptyState text="Upload a CSV or Excel file to create your first reusable data source." action="Upload data" onAction={() => uploadInput.current?.click()} />}</section>
    </div></div>;
}

function DataAssistant({ datasets, onCreate }: { datasets: Dataset[]; onCreate: () => void }) {
  const [datasetId, setDatasetId] = useState<number | null>(datasets[0]?.id || null);
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Array<{ question: string; answer: string }>>([]);
  const [busy, setBusy] = useState(false);
  const dataset = datasets.find((item) => item.id === datasetId);

  async function ask() {
    if (!dataset || !question.trim()) return;
    setBusy(true);
    const prompt = question.trim();
    try {
      const table = dataset.profile.tables[0];
      const dimension = table.dimensions.find((field) => prompt.toLowerCase().includes(field.toLowerCase())) || table.dimensions[0];
      const metric = table.metrics[0] || table.column_profiles.find((field) => field.semantic_type === "identifier")?.name || table.column_profiles[0]?.name;
      if (!metric) throw new Error("No queryable field was found.");
      const result = await api.query(dataset.id, { table_id: table.id, group_by: dimension, metric, aggregation: table.metrics.length ? "avg" : "count", sort: "desc", limit: 8 });
      const answer = result.categories?.length ? `${result.categories[0]} is the leading ${dimension || "segment"} in this result (${Number(result.values?.[0] || 0).toLocaleString()}). I queried ${result.categories.length} groups from ${dataset.name}.` : `The result is ${Number(result.value || 0).toLocaleString()} based on ${dataset.name}.`;
      setAnswers((current) => [...current, { question: prompt, answer }]); setQuestion("");
    } catch (caught) { setAnswers((current) => [...current, { question: prompt, answer: caught instanceof Error ? caught.message : "I could not query this source." }]); }
    finally { setBusy(false); }
  }

  return <div className="assistant-page"><header><div className="assistant-orb"><Sparkles size={22} /></div><p className="eyebrow">TEXT2BI DATA ASSISTANT</p><h1>Ask questions. Get evidence.</h1><span>Select a source and explore it conversationally before adding insights to a dashboard.</span></header><div className="assistant-source"><label>Data source<select value={datasetId || ""} onChange={(event) => setDatasetId(Number(event.target.value))}><option value="">Choose a source</option>{datasets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{dataset && <span>{dataset.row_count.toLocaleString()} rows available</span>}</div><section className="assistant-thread">{!answers.length && <div className="assistant-empty"><Bot size={28} /><h2>What would you like to know?</h2><p>Try “Which department is largest?” or “Show the leading entity.”</p><div><button onClick={() => setQuestion("Which department is largest?")}>Which department is largest?</button><button onClick={() => setQuestion("Show the leading entity")}>Show the leading entity</button></div></div>}{answers.map((item, index) => <div className="assistant-exchange" key={index}><p className="assistant-question">{item.question}</p><article><Sparkles size={16} /><div><strong>Answer from your data</strong><p>{item.answer}</p><button onClick={onCreate}><Plus size={13} /> Build a dashboard from this</button></div></article></div>)}</section><footer className="assistant-composer"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={datasets.length ? "Ask a question about your data…" : "Upload a data source first…"} disabled={!dataset || busy} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void ask(); } }} /><button onClick={() => void ask()} disabled={!dataset || !question.trim() || busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}</button></footer></div>;
}

function EmptyState({ text, action, onAction }: { text: string; action?: string; onAction?: () => void }) {
  return <div className="library-empty"><span>{text}</span>{action && <button onClick={onAction}>{action}</button>}</div>;
}

export default App;
