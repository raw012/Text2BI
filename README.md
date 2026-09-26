# Text2BI

Text2BI is an iterative, schema-driven AI Business Intelligence system. Users
upload CSV or Excel data, describe a business goal, and receive an evaluated,
editable React + Apache ECharts dashboard. The system can refine only the
affected agent stages instead of regenerating the entire dashboard.

It now operates as a persistent analytics workspace rather than a one-time
generator. Uploaded datasets and generated dashboards remain available in
libraries, dataset replacements are versioned and schema-checked, and the
Dashboard Copilot applies focused changes to an existing report.

## Product workspace

The React application contains four persistent work areas:

- **Home** summarizes saved dashboards, reusable data sources, available rows,
  and evaluated reports.
- **Dashboards** stores every generated multi-chart report and restores it for
  filtering, export, or AI refinement.
- **Data sources** previews real rows and supports safe file replacement. Before
  activating a replacement, the backend verifies every field referenced by an
  existing dashboard.
- **Ask your data** runs evidence-based aggregate questions against a selected
  source and can start a new dashboard workflow from the result.

Inside a dashboard, **Dashboard Copilot** is deliberately separate from the BI
canvas. It opens as a right-side conversational control surface, shows the
current report and revision, offers targeted change prompts, and creates a new
evaluated revision instead of behaving like another report card.

The workspace navigation remains visible while creating, viewing, or editing a
dashboard. The breadcrumb returns to the dashboard library without losing the
saved report. A new dashboard can start from an existing Text2BI data source, a
new CSV/Excel upload, or a PostgreSQL, MySQL/MariaDB, or SQLite table snapshot.

Data-source names are unique in the normal workspace view. Uploading the same
filename again updates the existing logical source and archives the previous
snapshot as a version. Likewise, the dashboard library shows only the latest
dashboard for each `(data source, title)` pair; historical database records are
preserved rather than deleted.

## Architecture

```mermaid
flowchart TD
  S[CSV / Excel / future connector] --> V[Versioned data source]
  V --> U[Dataset + request]
  V --> Q[Ask your data]
  U --> D[Data Analyst]
  D -->|DataAnalysisSpec| B[Business Analyst]
  B -->|KPIFormulaSpec| K[Deterministic KPI calculator]
  K -->|KPIResultSet| I[BI Designer]
  I -->|DashboardSchema| R[Preview renderer]
  R -->|HTML + computed chart data| E[BI Evaluation]
  E -->|Passed| P[Publish result]
  E -->|Visual or usability issue| I
  E -->|Business requirement issue| B
  E -->|Data issue| D
  P --> F[React + ECharts]
  P --> H[Downloadable HTML]
  F --> C[Dashboard Copilot]
  C --> D
  C --> B
  C --> I
```

Evaluation runs for at most five automatic iterations. If the fifth iteration
still has blocking issues, Text2BI publishes the best available result with
`needs_user_review`. The user can download it and start a new targeted revision
through the chat panel.

## Agent skills

Runtime instructions live in `backend/skills`:

- `data_analysis/SKILL.md`: dataset understanding, data quality, metric
  foundations, and time capabilities.
- `business_analysis/SKILL.md`: audience, objectives, supported KPI definitions,
  comparisons, and analytical questions.
- `bi_design/SKILL.md`: branding, logo placement, theme, layout, chart selection,
  filters, and preference-aware refinement.
- `bi_evaluation/SKILL.md`: visual, data, requirement, and usability evaluation.

The LLM reasons and plans from these skills. Deterministic code performs
calculation and validation:

- `backend/app/agent_tools/analysis.py`
- `backend/app/agent_tools/business.py`
- `backend/app/agent_tools/kpi.py`
- `backend/app/agent_tools/dashboard.py`
- `backend/app/services/visual_service.py`

## Data integrity

Every agent follows the same rules:

- Use only fields and values from the uploaded dataset.
- Do not create missing records, unsupported KPIs, or fictitious trends.
- Calculate KPI and chart values with Pandas/SQL-compatible tools, not the LLM.
- Validate every component query against the uploaded schema.
- Generate insights only from executed query results and retain their evidence.

The LLM never writes dashboard HTML. The intermediate contract is always:

```text
LLM reasoning → DashboardSchema JSON → query execution → React/ECharts or HTML renderer
```

## Typed contracts

Pydantic models are defined in `backend/app/schemas.py`:

- `DataAnalysisSpec`
- `BusinessAnalysisSpec`
- `KPIFormulaSpec`
- `KPIResultSet`
- `DashboardSchema`
- `EvaluationResult`
- `RenderArtifact`

Each evaluation issue contains:

```json
{
  "issue_category": "visual",
  "severity": "high",
  "description": "Two cards overlap in the 12-column layout.",
  "recommended_action": "Reflow only the affected components.",
  "target_agent": "bi_designer",
  "component_id": "comparison-department"
}
```

## Qwen configuration

Text2BI uses the Qwen DashScope OpenAI-compatible endpoint. Copy
`backend/.env.example` to `backend/.env`:

```dotenv
QWEN_API_KEY=your-dashscope-key
QWEN_MODEL=qwen-plus
QWEN_VL_MODEL=qwen-vl-max
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DATABASE_URL=sqlite:///./text2bi.db
FRONTEND_ORIGIN=http://localhost:5173
MAX_UPLOAD_MB=25
MAX_WORKFLOW_ITERATIONS=5
```

Qwen handles semantic reasoning and planning. Qwen-VL reviews a real Chromium
screenshot for visual/usability issues. Python remains authoritative for data
profiling, formulas, MoM/YoY, query execution, and evaluation scoring. When
`QWEN_API_KEY` is absent, deterministic fallbacks keep the workflow available.
The same client can target a self-hosted Qwen vLLM OpenAI-compatible endpoint by
changing `QWEN_BASE_URL`, `QWEN_MODEL`, and `QWEN_VL_MODEL`.

Month, quarter, year, MoM, and YoY components are created only when the request
explicitly asks for time analysis and the uploaded data supports it. They are
not added as generic dashboard defaults.

## Phase 1: AWS-ready deployment

The backend supports private S3 upload storage when `UPLOAD_BUCKET` is set.
Dataset manifests, source files, and logos are shared between container tasks
through S3; local development still uses `backend/uploads`. `DB_HOST`,
`DB_NAME`, `DB_USERNAME`, and a secret-injected `DB_PASSWORD` connect to RDS.
The deployed frontend calls the backend through its `/api` proxy on one HTTPS
origin. See [infra/README.md](infra/README.md) for the foundation/application
stacks, deployment order, required inputs, and current limitations. AWS
deployment and its live smoke tests remain pending a non-root deployment profile.

## One-command start

Put the Qwen key in `backend/.env`, then run from the repository root:

```bash
docker compose up --build
```

This starts PostgreSQL, the FastAPI/LangGraph backend (including Chromium for
screenshot evaluation), and the React frontend. Open `http://localhost:5173`.
Stop it with `docker compose down`; uploaded files and PostgreSQL data remain in
named Docker volumes.

## Native development

Requirements: Python 3.11+, Node 20+, npm.

### Backend

```bash
cd text2bi/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

If port `8000` is already used by another local application, run Text2BI on
`8001` and set `frontend/.env` to `VITE_API_URL=http://127.0.0.1:8001`. This
repository currently uses that conflict-free local setting.

SQLite is the default. To use PostgreSQL:

```bash
cd text2bi
docker compose up -d postgres
```

Then set:

```dotenv
DATABASE_URL=postgresql+psycopg://text2bi:text2bi@localhost:5432/text2bi
```

### Frontend

```bash
cd text2bi/frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173`, select one or more CSV/XLS/XLSX files, optionally
add a logo, describe the dashboard goal, and select **Generate dashboard**.

## User workflow

1. Upload one or more CSV/XLS/XLSX files and an optional logo. The source is
   stored in the Data Sources library. Every Excel sheet
   becomes a separate table; Text2BI does not guess cross-table joins.
2. Describe the business goal in one request field.
3. Follow the live agent progress while the chat is locked during analysis, KPI
   calculation, design, Chromium render, Qwen-VL review, and up to five targeted
   refinements. Progress comes from the running LangGraph nodes rather than a
   decorative timer.
4. Review the result status and evidence-backed insights.
5. Download the result as HTML.
6. Once the result is visible, open Dashboard Copilot to request a targeted
   chart, KPI, filter, or layout revision. The Copilot locks again while the request is routed to Data Analyst,
   Business Analyst, or BI Designer and re-evaluated. Every accepted response is
   stored as a new dashboard revision.
7. Replace a source file from the Data Sources workspace when new data arrives.
   Text2BI archives the previous version and rejects replacements that would
   remove fields used by existing dashboards, preserving their general layout.

The downloaded HTML is a self-contained interactive report. It embeds the
dashboard schema, brand asset, and only the source columns required by the
dashboard's filters, component queries, and governed KPI formulas. It does not
depend on the Text2BI backend or a chart CDN after download. Filter selections
recalculate chart series and evidence-backed insights locally in the browser.
Because those selected source columns are embedded, treat the downloaded file
as data-bearing and share it under the same access rules as the uploaded
dataset.

KPI results with `insufficient_data`, `unsupported`, or `error` status are never
replaced with a base aggregate. They are removed from the published view, and
ratio/period-growth units come from the formula rather than the source field
name.

If no logo is uploaded and the request explicitly names a company, the backend
first checks the company's public HTTPS website for a usable icon. If none is
available, it creates a clearly custom, color-matched initials mark and labels
the dashboard schema with `logo_source: "custom_mark"`; it never claims that
generated mark is an official logo.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/datasets` | List persistent data sources |
| `GET` | `/datasets/{id}` | Retrieve a data source and semantic profile |
| `GET` | `/datasets/{id}/preview` | Preview governed source rows |
| `POST` | `/datasets/{id}/replace` | Validate and activate a new source version |
| `GET` | `/datasets/{id}/versions` | List archived dataset versions |
| `POST` | `/upload_dataset` | Profile multiple CSV/XLS/XLSX files and sheets |
| `POST` | `/connect_database` | Import a PostgreSQL, MySQL/MariaDB, or SQLite table snapshot without storing credentials |
| `POST` | `/upload_logo` | Store an optional dashboard logo |
| `POST` | `/generate_dashboard` | Run the iterative multi-agent workflow |
| `POST` | `/workflow_runs/generate` | Start generation without blocking the browser |
| `GET` | `/workflow_runs/{run_id}` | Poll real LangGraph node and iteration progress |
| `POST` | `/dashboards/{id}/workflow_runs` | Start a targeted chat refinement |
| `GET` | `/dashboards/{id}` | Restore a generated dashboard in the browser |
| `GET` | `/dashboards` | List saved dashboards for the workspace library |
| `POST` | `/dashboards/{id}/chat` | Start a targeted, evaluated revision |
| `GET` | `/dashboards/{id}/messages` | Retrieve persisted chat history |
| `GET` | `/dashboards/{id}/download` | Download the current result as HTML |
| `POST` | `/modify_dashboard` | Save directly edited Dashboard JSON |
| `POST` | `/generate_insights` | Retrieve evidence-backed insights |
| `GET` | `/query` | Execute a safe schema-defined aggregation |
| `GET` | `/filter_options` | Populate interactive filter options |

Interactive API documentation is available at `http://127.0.0.1:8001/docs`
for the current native-development configuration.

## Current connector roadmap

CSV, Excel, and one-time PostgreSQL, MySQL/MariaDB, and SQLite table snapshots
are implemented. Database credentials are used only for the import request and
are not persisted. The Data Sources workspace and versioned dataset contract
are the base for scheduled Google Sheets, Snowflake, and Databricks connectors.
Production connector work still requires encrypted credential storage,
tenant-level permissions, refresh jobs, lineage, and schema drift mapping.

## Validation

Backend syntax:

```bash
cd text2bi/backend
.venv/bin/python -m compileall -q app
```

Frontend:

```bash
cd text2bi/frontend
npm run build
```

Before production use, add authentication, tenant isolation, object storage,
database migrations, audit retention, PII redaction, governed warehouse queries,
and model tracing/evaluation.
