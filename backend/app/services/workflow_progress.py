from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4


_runs: dict[str, dict[str, Any]] = {}
_lock = RLock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_workflow_run(kind: str) -> dict[str, Any]:
    run_id = uuid4().hex
    record = {
        "run_id": run_id,
        "kind": kind,
        "status": "queued",
        "node": "queued",
        "stage": "Preparing workflow",
        "message": "Your request has been queued.",
        "progress": 1,
        "iteration": 0,
        "max_iterations": 5,
        "result": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _lock:
        _runs[run_id] = record
    return deepcopy(record)


def update_workflow_run(run_id: str | None, **changes: Any) -> None:
    if not run_id:
        return
    with _lock:
        record = _runs.get(run_id)
        if not record:
            return
        record.update(changes)
        record["updated_at"] = _now()


def get_workflow_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        record = _runs.get(run_id)
        return deepcopy(record) if record else None


def fail_workflow_run(run_id: str, error: str) -> None:
    update_workflow_run(
        run_id,
        status="failed",
        node="failed",
        stage="Workflow stopped",
        message="The workflow could not be completed.",
        error=error,
    )
