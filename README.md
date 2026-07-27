# Text2BI

Text2BI is a schema-driven, AI-powered Business Intelligence MVP. Upload CSV or
Excel data, describe a business question, and receive an editable interactive
dashboard rendered with React and Apache ECharts.

## Architecture

The backend separates data computation from dashboard presentation. Pandas
profiles and queries the uploaded file. Four LangGraph nodes progressively
enrich a typed state, and the BI Designer emits `DashboardSchema` JSON—not HTML.
The React application interprets that schema and provides chart, title,
aggregation, filter, and theme controls.

```mermaid
flowchart LR
  U[Dataset + request] --> D[Data Analyst]
  D --> B[Business Analyst]
  B --> I[BI Designer]
  I --> C[Critic]
  C --> J[Dashboard JSON]
  J --> R[React + ECharts renderer]
  R --> E[Editable BI report]
  P[(PostgreSQL / SQLite)] <--> D
  P <--> J
```

- **Data Analyst:** profiles types, missing values, uniqueness, metrics,
  dimensions, dates, and candidate KPIs.
- **Business Analyst:** translates the user's goal into KPIs and decision
  questions.
- **BI Designer:** chooses chart types, layout, filters, theme tokens, and emits
  a validated Dashboard JSON schema.
- **Critic:** checks coverage, visual fit, and information hierarchy, assigning a
  quality score and review notes.

If `OPENAI_API_KEY` is absent, the complete flow runs with deterministic
heuristics. With a key, the analyst nodes use OpenAI for structured enrichment
while preserving the same API and schema contract.

## Run locally

Requirements: Python 3.11+, Node 20+, npm.

### Backend

```bash
cd text2bi/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The default local database is SQLite. For PostgreSQL:

```bash
cd text2bi
docker compose up -d postgres
```

Then set this in `backend/.env`:

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

Open `http://localhost:5173`, upload
`sample_data/employee_information.csv`, describe the view you need, and select
**Generate dashboard**.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/upload_dataset` | Validate, store, and profile CSV/XLS/XLSX |
| `POST` | `/generate_dashboard` | Run the four-agent workflow |
| `POST` | `/modify_dashboard` | Save edited JSON or refine it from an instruction |
| `POST` | `/generate_insights` | Retrieve generated business insights |
| `GET` | `/query` | Execute a safe schema-defined chart aggregation |
| `GET` | `/filter_options` | Populate interactive dimension filters |

Interactive API documentation is available at `http://localhost:8000/docs`.

## Dashboard JSON

The schema is defined in `backend/app/schemas.py`. Its main sections are:

```json
{
  "version": "1.0",
  "title": "Workforce overview",
  "dataset_id": 1,
  "theme": { "primary": "#2563EB", "background": "#F4F7FB" },
  "filters": [{ "field": "Department", "type": "select" }],
  "components": [{
    "id": "chart-segment",
    "type": "bar",
    "query": {
      "group_by": "Department",
      "metric": "Service Years",
      "aggregation": "sum"
    },
    "layout": { "x": 0, "y": 2, "w": 7, "h": 5 }
  }],
  "insights": [],
  "quality_score": 94,
  "critic_notes": []
}
```

## Production notes

- Store uploads in object storage and retain only object keys in PostgreSQL.
- Run profiling and LLM workflows in a queue for large files.
- Add authentication, tenant IDs, row-level security, and audit history.
- Replace direct Pandas queries with governed SQL models for warehouse-scale
  deployments.
- Pin allowed OpenAI models, add tracing/evaluations, and redact sensitive
  columns before prompts.
