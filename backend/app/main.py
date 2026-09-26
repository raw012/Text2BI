from pathlib import Path
from threading import Thread
from uuid import uuid4

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import MetaData, Table, create_engine as create_source_engine, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .agent_tools.dashboard import prepare_dashboard_for_display, render_dashboard
from .agents.workflow import dashboard_workflow
from .config import settings
from .database import Base, SessionLocal, database_url, engine, get_db
from .models import Dashboard, DashboardMessage, DashboardRun, Dataset, DatasetVersion, LiveConnection
from .schemas import (
    ChatRefinementRequest,
    ChatRefinementResponse,
    DashboardSchema,
    DatabaseImportRequest,
    LiveConnectionRequest,
    LiveQuestionRequest,
    DatasetResponse,
    GenerateDashboardRequest,
    GenerateDashboardResponse,
    InsightsRequest,
    ModifyDashboardRequest,
    QuerySchema,
)
from .services.data_service import execute_query
from .services.object_storage import persist_file, read_logo
from .services.live_database import (
    ask_live, delete_secret, load_secret, save_secret, source_schema,
    validate_tables, validate_url,
)
from .services.data_service import (
    discover_file_tables,
    profile_dataset_tables,
    read_dataset_tables,
    table_slug,
    write_dataset_manifest,
)
from .services.brand_service import infer_brand_identity, resolve_brand_assets
from .services.report_template_service import list_report_templates
from .services.workflow_progress import (
    create_workflow_run,
    fail_workflow_run,
    get_workflow_run,
    update_workflow_run,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, version="0.2.0", root_path=settings.api_root_path)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/uploads/{name}")
def uploaded_logo(name: str):
    try:
        content = read_logo(name)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Logo not found") from None
    suffix = Path(name).suffix.lower()
    mime = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon"}
    return Response(content, media_type=mime.get(suffix, "application/octet-stream"))


def _latest_run(db: Session, dashboard_id: int) -> DashboardRun | None:
    return (
        db.query(DashboardRun)
        .filter(DashboardRun.dashboard_id == dashboard_id)
        .order_by(DashboardRun.id.desc())
        .first()
    )


def _workflow_input(
    dataset: Dataset,
    request: str,
    *,
    current_dashboard: dict | None = None,
    data_analysis: dict | None = None,
    business_analysis: dict | None = None,
    feedback: str | None = None,
    logo_url: str | None = None,
    logo_source: str | None = None,
    brand_identity: dict | None = None,
    preferences: str | None = None,
    run_id: str | None = None,
) -> dict:
    payload = {
        "dataset_id": dataset.id,
        "dataset_file_path": dataset.file_path,
        "profile": dataset.profile,
        "business_request": request,
        "logo_url": logo_url,
        "logo_source": logo_source,
        "brand_identity": brand_identity,
        "user_preferences": preferences,
        "user_feedback": feedback,
        "current_dashboard": current_dashboard,
        "iteration": 0,
    }
    if run_id:
        payload["run_id"] = run_id
    if data_analysis:
        payload["data_analysis"] = data_analysis
    if business_analysis:
        payload["business_analysis"] = business_analysis
    return payload


def _save_run(db: Session, dashboard_id: int, result: dict) -> DashboardRun:
    evaluation = result["evaluation"]
    run = DashboardRun(
        dashboard_id=dashboard_id,
        data_analysis=result["data_analysis"],
        business_analysis=result["business_analysis"],
        evaluation=evaluation,
        iteration_count=result["iteration"],
        status=evaluation["status"],
    )
    db.add(run)
    return run


def _persist_new_dashboard(
    db: Session,
    dataset: Dataset,
    business_request: str,
    result: dict,
) -> tuple[Dashboard, DashboardSchema]:
    schema = DashboardSchema.model_validate(result["dashboard"])
    dashboard = Dashboard(
        dataset_id=dataset.id,
        title=schema.title,
        business_request=business_request,
        schema=schema.model_dump(mode="json"),
    )
    db.add(dashboard)
    db.flush()
    _save_run(db, dashboard.id, result)
    db.commit()
    db.refresh(dashboard)
    return dashboard, schema


def _brand_context(
    business_request: str,
    uploaded_logo_url: str | None,
) -> tuple[str | None, dict | None, str | None]:
    if uploaded_logo_url:
        identity = infer_brand_identity(business_request)
        return (
            uploaded_logo_url,
            identity.model_dump(mode="json") if identity else None,
            "uploaded",
        )
    return resolve_brand_assets(business_request)


def _run_generate_background(run_id: str, payload: dict) -> None:
    try:
        update_workflow_run(
            run_id,
            status="running",
            node="brand_identity",
            stage="Brand identity",
            message="Preparing the company identity and logo.",
            progress=2,
        )
        with SessionLocal() as db:
            dataset = db.get(Dataset, payload["dataset_id"])
            if not dataset:
                raise ValueError("Dataset not found.")
            logo_url, brand_identity, logo_source = _brand_context(
                payload["business_request"],
                payload.get("logo_url"),
            )
            result = dashboard_workflow.invoke(
                _workflow_input(
                    dataset,
                    payload["business_request"],
                    logo_url=logo_url,
                    logo_source=logo_source,
                    brand_identity=brand_identity,
                    run_id=run_id,
                ),
                config={"recursion_limit": 60},
            )
            dashboard, schema = _persist_new_dashboard(
                db,
                dataset,
                payload["business_request"],
                result,
            )
        update_workflow_run(
            run_id,
            status="completed",
            node="published",
            stage="Dashboard ready",
            message="The evaluated dashboard is ready for review.",
            progress=100,
            iteration=result["iteration"],
            result={
                "dashboard_id": dashboard.id,
                "dashboard": schema.model_dump(mode="json"),
            },
        )
    except Exception as exc:
        fail_workflow_run(run_id, str(exc))


def _run_chat_background(run_id: str, dashboard_id: int, message: str) -> None:
    try:
        with SessionLocal() as db:
            record = db.get(Dashboard, dashboard_id)
            if not record:
                raise ValueError("Dashboard not found.")
            dataset = db.get(Dataset, record.dataset_id)
            previous_run = _latest_run(db, record.id)
            if not dataset or not previous_run:
                raise ValueError("Dashboard workflow context is unavailable.")
            current = DashboardSchema.model_validate(record.schema)
            brand_identity = (
                {
                    "company_name": current.company_name,
                    "primary_color": current.theme.get("primary", "#111827"),
                    "accent_color": current.theme.get("accent", "#00ADEF"),
                }
                if current.company_name
                else None
            )
            result = dashboard_workflow.invoke(
                _workflow_input(
                    dataset,
                    record.business_request,
                    current_dashboard=current.model_dump(mode="json"),
                    data_analysis=previous_run.data_analysis,
                    business_analysis=previous_run.business_analysis,
                    feedback=message,
                    logo_url=current.logo_url,
                    logo_source=current.logo_source,
                    brand_identity=brand_identity,
                    run_id=run_id,
                ),
                config={"recursion_limit": 60},
            )
            schema = DashboardSchema.model_validate(result["dashboard"])
            record.title = schema.title
            record.schema = schema.model_dump(mode="json")
            _save_run(db, record.id, result)
            db.add(DashboardMessage(dashboard_id=record.id, role="user", content=message))
            assistant_message = (
                f"Revision {schema.revision} is ready with status {schema.workflow_status} "
                f"and score {schema.quality_score}/100."
            )
            db.add(
                DashboardMessage(
                    dashboard_id=record.id,
                    role="assistant",
                    content=assistant_message,
                )
            )
            db.commit()
        update_workflow_run(
            run_id,
            status="completed",
            node="published",
            stage="Revision ready",
            message="The evaluated revision is ready.",
            progress=100,
            iteration=result["iteration"],
            result={
                "dashboard_id": dashboard_id,
                "message": assistant_message,
                "dashboard": schema.model_dump(mode="json"),
            },
        )
    except Exception as exc:
        fail_workflow_run(run_id, str(exc))


@app.get("/health")
def health():
    return {"status": "ok", "mode": "qwen" if settings.qwen_api_key else "heuristic"}


@app.get("/live_connections")
def list_live_connections(db: Session = Depends(get_db)):
    records = db.query(LiveConnection).order_by(LiveConnection.created_at.desc()).all()
    return [{"id": item.id, "name": item.name, "allowed_tables": item.allowed_tables}
            for item in records]


@app.post("/live_connections", status_code=201)
def create_live_connection(payload: LiveConnectionRequest, db: Session = Depends(get_db)):
    if not settings.live_connection_secret_prefix:
        raise HTTPException(503, "Live connection secret storage is not configured.")
    try:
        validate_url(payload.database_url)
        tables = validate_tables(payload.allowed_tables)
        source_schema(payload.database_url, tables, require_readonly=True)
    except Exception as exc:
        raise HTTPException(400, "Connection must use an accessible read-only PostgreSQL role and allowed tables.") from exc
    arn = None
    try:
        arn = save_secret(payload.database_url)
        record = LiveConnection(name=payload.name, secret_arn=arn, allowed_tables=tables)
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        if arn:
            try:
                delete_secret(arn)
            except Exception:
                pass
        raise HTTPException(502, "Could not save the connection securely.") from None
    return {"id": record.id, "name": record.name, "allowed_tables": record.allowed_tables}


@app.get("/live_connections/{connection_id}/schema")
def live_connection_schema(connection_id: int, db: Session = Depends(get_db)):
    record = db.get(LiveConnection, connection_id)
    if not record:
        raise HTTPException(404, "Live connection not found.")
    try:
        return {"tables": source_schema(load_secret(record.secret_arn), record.allowed_tables)}
    except Exception:
        raise HTTPException(502, "Could not inspect the live database.") from None


@app.post("/live_connections/{connection_id}/ask")
def ask_live_connection(
    connection_id: int,
    payload: LiveQuestionRequest,
    db: Session = Depends(get_db),
):
    record = db.get(LiveConnection, connection_id)
    if not record:
        raise HTTPException(404, "Live connection not found.")
    try:
        return ask_live(record.secret_arn, record.allowed_tables, payload.question)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        raise HTTPException(502, "The governed query could not be completed.") from None


@app.delete("/live_connections/{connection_id}", status_code=204)
def remove_live_connection(connection_id: int, db: Session = Depends(get_db)):
    record = db.get(LiveConnection, connection_id)
    if not record:
        raise HTTPException(404, "Live connection not found.")
    try:
        delete_secret(record.secret_arn)
    except Exception:
        raise HTTPException(502, "Could not schedule credential deletion.") from None
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@app.get("/datasets", response_model=list[DatasetResponse])
def list_datasets(db: Session = Depends(get_db)):
    records = db.query(Dataset).order_by(Dataset.created_at.desc()).all()
    seen: set[str] = set()
    unique: list[Dataset] = []
    for record in records:
        key = record.name.strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


@app.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    return dataset


@app.get("/datasets/{dataset_id}/preview")
def preview_dataset(
    dataset_id: int,
    table_id: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    tables = read_dataset_tables(dataset.file_path)
    selected_id = table_id or next(iter(tables), None)
    if not selected_id or selected_id not in tables:
        raise HTTPException(404, "Table not found.")
    frame = tables[selected_id].head(limit).copy()
    frame = frame.astype(object).where(frame.notna(), None)
    return {
        "dataset_id": dataset.id,
        "table_id": selected_id,
        "columns": [str(column) for column in frame.columns],
        "rows": frame.to_dict(orient="records"),
        "total_rows": len(tables[selected_id]),
    }


def _archive_dataset_version(db: Session, dataset: Dataset, operation: str) -> None:
    version_count = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .count()
    )
    db.add(
        DatasetVersion(
            dataset_id=dataset.id,
            version=version_count + 1,
            file_path=dataset.file_path,
            row_count=dataset.row_count,
            column_count=dataset.column_count,
            profile=dataset.profile,
            operation=operation,
        )
    )


def _missing_dashboard_fields(
    db: Session,
    dataset: Dataset,
    tables: dict[str, pd.DataFrame],
) -> list[str]:
    required: dict[str, set[str]] = {}
    dashboards = db.query(Dashboard).filter(Dashboard.dataset_id == dataset.id).all()
    for dashboard in dashboards:
        schema = DashboardSchema.model_validate(dashboard.schema)
        for filter_spec in schema.filters:
            required.setdefault(filter_spec.table_id, set()).add(filter_spec.field)
        for component in schema.components:
            required.setdefault(component.query.table_id, set()).add(component.query.metric)
            if component.query.group_by:
                required[component.query.table_id].add(component.query.group_by)
    return [
        f"{table_id}.{field}"
        for table_id, fields in required.items()
        for field in fields
        if table_id not in tables or field not in tables[table_id].columns
    ]
@app.get("/datasets/{dataset_id}/versions")
def dataset_versions(dataset_id: int, db: Session = Depends(get_db)):
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, "Dataset not found.")
    versions = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version.desc())
        .all()
    )
    return {
        "versions": [
            {
                "id": item.id,
                "version": item.version,
                "operation": item.operation,
                "row_count": item.row_count,
                "column_count": item.column_count,
                "created_at": item.created_at,
            }
            for item in versions
        ]
    }


@app.post("/upload_dataset", response_model=DatasetResponse)
async def upload_dataset(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(400, "Upload at least one CSV or Excel file.")
    entries: list[dict] = []
    used_ids: set[str] = set()
    try:
        for file in files:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".csv", ".xlsx", ".xls"}:
                raise ValueError(f"{file.filename}: only CSV and Excel files are supported.")
            content = await file.read()
            if len(content) > settings.max_upload_mb * 1024 * 1024:
                raise ValueError(f"{file.filename} exceeds {settings.max_upload_mb} MB.")
            path = settings.upload_dir / f"{uuid4().hex}{suffix}"
            path.write_bytes(content)
            entries.extend(
                discover_file_tables(
                    path,
                    file.filename or path.name,
                    used_ids,
                )
            )
        manifest = write_dataset_manifest(
            entries,
            settings.upload_dir / f"dataset-{uuid4().hex}.json",
        )
        tables = read_dataset_tables(manifest)
        empty = [table_id for table_id, frame in tables.items() if frame.empty]
        if empty:
            raise ValueError(f"Empty tables: {', '.join(empty)}")
        profile = profile_dataset_tables(tables, entries)
    except Exception as exc:
        raise HTTPException(400, f"Could not read dataset: {exc}") from exc

    names = [file.filename or "dataset" for file in files]
    display_name = names[0] if len(names) == 1 else f"{names[0]} + {len(names) - 1} more"
    existing = next(
        (
            record
            for record in db.query(Dataset).order_by(Dataset.created_at.desc()).all()
            if record.name.strip().casefold() == display_name.strip().casefold()
        ),
        None,
    )
    if existing:
        old_table_ids = [table["id"] for table in existing.profile.get("tables", [])]
        if len(old_table_ids) == len(entries):
            for entry, old_id in zip(entries, old_table_ids, strict=True):
                entry["id"] = old_id
            manifest = write_dataset_manifest(entries, manifest)
            tables = read_dataset_tables(manifest)
            profile = profile_dataset_tables(tables, entries)
        missing = _missing_dashboard_fields(db, existing, tables)
        if missing:
            raise HTTPException(
                409,
                "Same-name upload would break existing dashboards. Missing fields: "
                + ", ".join(missing[:12]),
            )
        _archive_dataset_version(db, existing, "same-name upload")
        existing.file_path = str(manifest)
        existing.row_count = profile.rows
        existing.column_count = profile.columns
        existing.profile = profile.model_dump()
        db.commit()
        db.refresh(existing)
        return existing

    dataset = Dataset(
        name=display_name,
        file_path=str(manifest),
        row_count=profile.rows,
        column_count=profile.columns,
        profile=profile.model_dump(),
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@app.post("/connect_database", response_model=DatasetResponse)
def connect_database(payload: DatabaseImportRequest, db: Session = Depends(get_db)):
    """Import a governed snapshot from one database table without storing credentials."""
    try:
        parsed = make_url(payload.database_url)
        if parsed.get_backend_name() not in {"postgresql", "mysql", "mariadb", "sqlite"}:
            raise ValueError("Supported databases are PostgreSQL, MySQL/MariaDB, and SQLite.")
        source = create_source_engine(payload.database_url, pool_pre_ping=True)
        inspector = inspect(source)
        available = inspector.get_table_names(schema=payload.schema_name)
        if payload.table_name not in available:
            raise ValueError(
                f"Table '{payload.table_name}' was not found. Available: {', '.join(available[:20])}"
            )
        metadata = MetaData()
        source_table = Table(
            payload.table_name,
            metadata,
            schema=payload.schema_name,
            autoload_with=source,
        )
        with source.connect() as connection:
            result = connection.execute(select(source_table).limit(payload.row_limit))
            frame = pd.DataFrame(result.fetchall(), columns=result.keys())
        source.dispose()
        if frame.empty:
            raise ValueError("The selected table is empty.")

        snapshot_path = settings.upload_dir / f"database-{uuid4().hex}.csv"
        frame.to_csv(snapshot_path, index=False)
        table_id = table_slug(payload.table_name)
        entry = {
            "id": table_id,
            "name": payload.table_name,
            "source_file": f"database:{payload.table_name}",
            "path": str(snapshot_path),
            "sheet_name": None,
        }
        manifest = write_dataset_manifest(
            [entry],
            settings.upload_dir / f"dataset-{uuid4().hex}.json",
        )
        profile = profile_dataset_tables({table_id: frame}, [entry])
    except Exception as exc:
        raise HTTPException(400, f"Could not import database table: {exc}") from exc

    display_name = payload.dataset_name or f"{parsed.database or 'database'} · {payload.table_name}"
    existing = next(
        (
            record
            for record in db.query(Dataset).order_by(Dataset.created_at.desc()).all()
            if record.name.strip().casefold() == display_name.strip().casefold()
        ),
        None,
    )
    if existing:
        missing = _missing_dashboard_fields(db, existing, {table_id: frame})
        if missing:
            raise HTTPException(
                409,
                "Database refresh would break existing dashboards. Missing fields: "
                + ", ".join(missing[:12]),
            )
        _archive_dataset_version(db, existing, "database refresh")
        existing.file_path = str(manifest)
        existing.row_count = profile.rows
        existing.column_count = profile.columns
        existing.profile = profile.model_dump()
        dataset = existing
    else:
        dataset = Dataset(
            name=display_name,
            file_path=str(manifest),
            row_count=profile.rows,
            column_count=profile.columns,
            profile=profile.model_dump(),
        )
        db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@app.post("/datasets/connect_curated_tlc", response_model=DatasetResponse)
def connect_curated_tlc(
    table: str = Query(default="tlc_daily", pattern="^(tlc_daily|tlc_pickup_zone)$"),
    db: Session = Depends(get_db),
):
    """Register a small Spark-curated serving table using server-side credentials."""
    url = (
        database_url.render_as_string(hide_password=False)
        if hasattr(database_url, "render_as_string") else str(database_url)
    )
    if not url.startswith("postgresql"):
        raise HTTPException(409, "The curated TLC connector requires PostgreSQL.")
    return connect_database(
        DatabaseImportRequest(
            database_url=url,
            schema_name="curated",
            table_name=table,
            dataset_name=f"NYC TLC · {table}",
        ),
        db,
    )


@app.post("/datasets/{dataset_id}/replace", response_model=DatasetResponse)
async def replace_dataset(
    dataset_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    if not files:
        raise HTTPException(400, "Upload at least one CSV or Excel file.")

    entries: list[dict] = []
    used_ids: set[str] = set()
    try:
        for file in files:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".csv", ".xlsx", ".xls"}:
                raise ValueError(f"{file.filename}: only CSV and Excel files are supported.")
            content = await file.read()
            if len(content) > settings.max_upload_mb * 1024 * 1024:
                raise ValueError(f"{file.filename} exceeds {settings.max_upload_mb} MB.")
            path = settings.upload_dir / f"{uuid4().hex}{suffix}"
            path.write_bytes(content)
            entries.extend(discover_file_tables(path, file.filename or path.name, used_ids))

        old_table_ids = [table["id"] for table in dataset.profile.get("tables", [])]
        if len(old_table_ids) == len(entries):
            for entry, old_id in zip(entries, old_table_ids, strict=True):
                entry["id"] = old_id
        manifest = write_dataset_manifest(
            entries,
            settings.upload_dir / f"dataset-{uuid4().hex}.json",
        )
        tables = read_dataset_tables(manifest)
        if any(frame.empty for frame in tables.values()):
            raise ValueError("Replacement contains an empty table.")

        required: dict[str, set[str]] = {}
        dashboards = db.query(Dashboard).filter(Dashboard.dataset_id == dataset.id).all()
        for dashboard in dashboards:
            schema = DashboardSchema.model_validate(dashboard.schema)
            for filter_spec in schema.filters:
                required.setdefault(filter_spec.table_id, set()).add(filter_spec.field)
            for component in schema.components:
                required.setdefault(component.query.table_id, set()).add(component.query.metric)
                if component.query.group_by:
                    required[component.query.table_id].add(component.query.group_by)
        missing = [
            f"{table_id}.{field}"
            for table_id, fields in required.items()
            for field in fields
            if table_id not in tables or field not in tables[table_id].columns
        ]
        if missing:
            raise ValueError(
                "Replacement would break existing dashboards. Missing fields: "
                + ", ".join(missing[:12])
            )
        profile = profile_dataset_tables(tables, entries)
    except Exception as exc:
        raise HTTPException(400, f"Could not replace dataset: {exc}") from exc

    _archive_dataset_version(db, dataset, "replace")
    dataset.name = files[0].filename or dataset.name
    dataset.file_path = str(manifest)
    dataset.row_count = profile.rows
    dataset.column_count = profile.columns
    dataset.profile = profile.model_dump()
    db.commit()
    db.refresh(dataset)
    return dataset


@app.post("/upload_logo")
async def upload_logo(request: Request, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        raise HTTPException(400, "Upload a PNG, JPG, WEBP, or SVG logo.")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Logo exceeds 5 MB.")
    name = f"logo-{uuid4().hex}{suffix}"
    path = settings.upload_dir / name
    path.write_bytes(content)
    persist_file(path, prefix="logos")
    return {"logo_url": str(request.base_url).rstrip("/") + f"/uploads/{name}"}


@app.post("/generate_dashboard", response_model=GenerateDashboardResponse)
def generate_dashboard(payload: GenerateDashboardRequest, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    logo_url, brand_identity, logo_source = _brand_context(
        payload.business_request,
        payload.logo_url,
    )
    result = dashboard_workflow.invoke(
        _workflow_input(
            dataset,
            payload.business_request,
            logo_url=logo_url,
            logo_source=logo_source,
            brand_identity=brand_identity,
        ),
        config={"recursion_limit": 60},
    )
    dashboard, schema = _persist_new_dashboard(
        db,
        dataset,
        payload.business_request,
        result,
    )
    return {"dashboard_id": dashboard.id, "dashboard": schema}


@app.post("/workflow_runs/generate")
def start_generate_workflow(payload: GenerateDashboardRequest, db: Session = Depends(get_db)):
    if not db.get(Dataset, payload.dataset_id):
        raise HTTPException(404, "Dataset not found.")
    run = create_workflow_run("generate")
    Thread(
        target=_run_generate_background,
        args=(run["run_id"], payload.model_dump(mode="json")),
        daemon=True,
    ).start()
    return run


@app.post("/dashboards/{dashboard_id}/workflow_runs")
def start_chat_workflow(
    dashboard_id: int,
    payload: ChatRefinementRequest,
    db: Session = Depends(get_db),
):
    if not db.get(Dashboard, dashboard_id):
        raise HTTPException(404, "Dashboard not found.")
    run = create_workflow_run("refine")
    Thread(
        target=_run_chat_background,
        args=(run["run_id"], dashboard_id, payload.message),
        daemon=True,
    ).start()
    return run


@app.get("/workflow_runs/{run_id}")
def workflow_run_status(run_id: str):
    run = get_workflow_run(run_id)
    if not run:
        raise HTTPException(404, "Workflow run not found.")
    return run


@app.get("/dashboards/{dashboard_id}", response_model=GenerateDashboardResponse)
def get_dashboard(dashboard_id: int, db: Session = Depends(get_db)):
    record = db.get(Dashboard, dashboard_id)
    if not record:
        raise HTTPException(404, "Dashboard not found.")
    return {
        "dashboard_id": record.id,
        "dashboard": prepare_dashboard_for_display(
            DashboardSchema.model_validate(record.schema)
        ),
    }


@app.get("/dashboards")
def list_dashboards(db: Session = Depends(get_db)):
    records = db.query(Dashboard).order_by(Dashboard.updated_at.desc()).all()
    seen: set[tuple[int, str]] = set()
    unique: list[Dashboard] = []
    for record in records:
        key = (record.dataset_id, record.title.strip().casefold())
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return {
        "dashboards": [
            {
                "id": record.id,
                "title": record.title,
                "dataset_id": record.dataset_id,
                "business_request": record.business_request,
                "component_count": len(record.schema.get("components", [])),
                "filter_count": len(record.schema.get("filters", [])),
                "status": record.schema.get("workflow_status", "draft"),
                "quality_score": record.schema.get("quality_score", 0),
                "updated_at": record.updated_at,
            }
            for record in unique
        ]
    }


@app.get("/report_templates")
def report_templates():
    return {"templates": list_report_templates()}


@app.post(
    "/dashboards/{dashboard_id}/chat",
    response_model=ChatRefinementResponse,
)
def refine_with_chat(
    dashboard_id: int,
    payload: ChatRefinementRequest,
    db: Session = Depends(get_db),
):
    record = db.get(Dashboard, dashboard_id)
    if not record:
        raise HTTPException(404, "Dashboard not found.")
    dataset = db.get(Dataset, record.dataset_id)
    run = _latest_run(db, record.id)
    if not dataset or not run:
        raise HTTPException(409, "Dashboard workflow context is unavailable.")
    current = DashboardSchema.model_validate(record.schema)
    result = dashboard_workflow.invoke(
        _workflow_input(
            dataset,
            record.business_request,
            current_dashboard=current.model_dump(mode="json"),
            data_analysis=run.data_analysis,
            business_analysis=run.business_analysis,
            feedback=payload.message,
            logo_url=current.logo_url,
        ),
        config={"recursion_limit": 60},
    )
    schema = DashboardSchema.model_validate(result["dashboard"])
    record.title = schema.title
    record.schema = schema.model_dump(mode="json")
    _save_run(db, record.id, result)
    db.add(DashboardMessage(dashboard_id=record.id, role="user", content=payload.message))
    assistant_message = (
        f"Revision {schema.revision} is ready with status {schema.workflow_status} "
        f"and score {schema.quality_score}/100."
    )
    db.add(DashboardMessage(dashboard_id=record.id, role="assistant", content=assistant_message))
    db.commit()
    return {
        "dashboard_id": record.id,
        "message": assistant_message,
        "dashboard": schema,
    }


@app.get("/dashboards/{dashboard_id}/messages")
def dashboard_messages(dashboard_id: int, db: Session = Depends(get_db)):
    if not db.get(Dashboard, dashboard_id):
        raise HTTPException(404, "Dashboard not found.")
    messages = (
        db.query(DashboardMessage)
        .filter(DashboardMessage.dashboard_id == dashboard_id)
        .order_by(DashboardMessage.id.asc())
        .all()
    )
    return {
        "messages": [
            {"id": item.id, "role": item.role, "content": item.content}
            for item in messages
        ]
    }


@app.get("/dashboards/{dashboard_id}/download")
def download_dashboard(
    dashboard_id: int,
    template_id: str = Query(default="generic-executive"),
    db: Session = Depends(get_db),
):
    record = db.get(Dashboard, dashboard_id)
    if not record:
        raise HTTPException(404, "Dashboard not found.")
    dataset = db.get(Dataset, record.dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    schema = DashboardSchema.model_validate(record.schema)
    try:
        rendered, artifact = render_dashboard(
            schema,
            read_dataset_tables(dataset.file_path),
            template_id=template_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    safe_name = "".join(character if character.isalnum() else "-" for character in rendered.title).strip("-")
    return Response(
        content=artifact.html,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{safe_name or "dashboard"}.html"'},
    )


@app.post("/modify_dashboard", response_model=GenerateDashboardResponse)
def modify_dashboard(payload: ModifyDashboardRequest, db: Session = Depends(get_db)):
    record = db.get(Dashboard, payload.dashboard_id)
    if not record:
        raise HTTPException(404, "Dashboard not found.")
    if payload.dashboard:
        schema = payload.dashboard
        record.title = schema.title
        record.schema = schema.model_dump(mode="json")
        db.commit()
        return {"dashboard_id": record.id, "dashboard": schema}
    if payload.instruction:
        refined = refine_with_chat(
            record.id,
            ChatRefinementRequest(message=payload.instruction),
            db,
        )
        return {"dashboard_id": record.id, "dashboard": refined["dashboard"]}
    raise HTTPException(400, "Provide an instruction or dashboard schema.")


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
    table_id: str = "main",
    aggregation: str = "sum",
    group_by: str | None = None,
    sort: str = "desc",
    filter_field: list[str] | None = Query(default=None),
    filter_value: list[str] | None = Query(default=None),
    limit: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    valid_fields = {
        (column.get("table_id", "main"), column["name"])
        for column in dataset.profile["column_profiles"]
    }
    if (table_id, metric) not in valid_fields or (
        group_by and (table_id, group_by) not in valid_fields
    ):
        raise HTTPException(400, "Query references an unknown field.")
    fields = filter_field or []
    values = filter_value or []
    if len(fields) != len(values) or any((table_id, field) not in valid_fields for field in fields):
        raise HTTPException(400, "Filters are invalid.")
    try:
        query = QuerySchema(
            table_id=table_id,
            metric=metric,
            aggregation=aggregation,
            group_by=group_by,
            sort=sort,
            limit=limit,
        )
        filters = dict(zip(fields, values, strict=True))
        tables = read_dataset_tables(dataset.file_path)
        if table_id not in tables:
            raise ValueError("Unknown table.")
        return execute_query(tables[table_id], query, filters)
    except Exception as exc:
        raise HTTPException(400, f"Could not execute query: {exc}") from exc


@app.get("/filter_options")
def filter_options(
    dataset_id: int,
    field: str,
    table_id: str = "main",
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    valid_fields = {
        (column.get("table_id", "main"), column["name"])
        for column in dataset.profile["column_profiles"]
    }
    if (table_id, field) not in valid_fields:
        raise HTTPException(400, "Unknown filter field.")
    tables = read_dataset_tables(dataset.file_path)
    values = tables[table_id][field].dropna().astype(str).value_counts().head(50).index
    return {"options": values.tolist()}
