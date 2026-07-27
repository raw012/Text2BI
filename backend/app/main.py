from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .agents.workflow import dashboard_workflow, modify_schema
from .config import settings
from .database import Base, engine, get_db
from .models import Dashboard, Dataset
from .schemas import (
    DashboardSchema,
    DatasetResponse,
    GenerateDashboardRequest,
    GenerateDashboardResponse,
    InsightsRequest,
    ModifyDashboardRequest,
    QuerySchema,
)
from .services.data_service import execute_query, profile_dataframe, read_dataframe

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "mode": "openai" if settings.openai_api_key else "heuristic"}


@app.get("/datasets", response_model=list[DatasetResponse])
def list_datasets(db: Session = Depends(get_db)):
    return db.query(Dataset).order_by(Dataset.created_at.desc()).all()


@app.post("/upload_dataset", response_model=DatasetResponse)
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(400, "Upload a CSV or Excel file.")
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB.")
    path = settings.upload_dir / f"{uuid4().hex}{suffix}"
    path.write_bytes(content)
    try:
        df = read_dataframe(path)
        if df.empty:
            raise ValueError("The file contains no rows.")
        profile = profile_dataframe(df)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read dataset: {exc}") from exc

    dataset = Dataset(
        name=file.filename or path.name,
        file_path=str(path),
        row_count=profile.rows,
        column_count=profile.columns,
        profile=profile.model_dump(),
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@app.post("/generate_dashboard", response_model=GenerateDashboardResponse)
def generate_dashboard(payload: GenerateDashboardRequest, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    result = dashboard_workflow.invoke(
        {
            "dataset_id": dataset.id,
            "profile": dataset.profile,
            "business_request": payload.business_request,
            "iteration": 0,
        }
    )
    schema = DashboardSchema.model_validate(result["dashboard"])
    dashboard = Dashboard(
        dataset_id=dataset.id,
        title=schema.title,
        business_request=payload.business_request,
        schema=schema.model_dump(),
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return {"dashboard_id": dashboard.id, "dashboard": schema}


@app.post("/modify_dashboard", response_model=GenerateDashboardResponse)
def modify_dashboard(payload: ModifyDashboardRequest, db: Session = Depends(get_db)):
    record = db.get(Dashboard, payload.dashboard_id)
    if not record:
        raise HTTPException(404, "Dashboard not found.")
    if payload.dashboard:
        schema = payload.dashboard
    elif payload.instruction:
        schema = DashboardSchema.model_validate(modify_schema(record.schema, payload.instruction))
    else:
        raise HTTPException(400, "Provide an instruction or dashboard schema.")
    record.title = schema.title
    record.schema = schema.model_dump()
    db.commit()
    return {"dashboard_id": record.id, "dashboard": schema}


@app.post("/generate_insights")
def generate_insights(payload: InsightsRequest, db: Session = Depends(get_db)):
    record = db.get(Dashboard, payload.dashboard_id)
    if not record:
        raise HTTPException(404, "Dashboard not found.")
    return {"dashboard_id": record.id, "insights": record.schema.get("insights", [])}


@app.get("/query")
def query_dataset(
    dataset_id: int,
    metric: str,
    aggregation: str = "sum",
    group_by: str | None = None,
    sort: str = "desc",
    filter_field: str | None = None,
    filter_value: str | None = None,
    limit: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    valid_fields = {column["name"] for column in dataset.profile["column_profiles"]}
    if metric not in valid_fields or (group_by and group_by not in valid_fields):
        raise HTTPException(400, "Query references an unknown field.")
    if filter_field and filter_field not in valid_fields:
        raise HTTPException(400, "Filter references an unknown field.")
    try:
        query = QuerySchema(
            metric=metric, aggregation=aggregation, group_by=group_by, sort=sort, limit=limit
        )
        filters = {filter_field: filter_value} if filter_field and filter_value else None
        return execute_query(read_dataframe(dataset.file_path), query, filters)
    except Exception as exc:
        raise HTTPException(400, f"Could not execute query: {exc}") from exc


@app.get("/filter_options")
def filter_options(
    dataset_id: int,
    field: str,
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    valid_fields = {column["name"] for column in dataset.profile["column_profiles"]}
    if field not in valid_fields:
        raise HTTPException(400, "Unknown filter field.")
    values = read_dataframe(dataset.file_path)[field].dropna().astype(str).value_counts().head(50).index
    return {"options": values.tolist()}
