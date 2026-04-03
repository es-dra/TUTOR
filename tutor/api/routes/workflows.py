"""FastAPI routes for workflow management."""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from ...core.workflow.base import WorkflowEngine, WorkflowStatus
from ...core.workflow.idea import IdeaFlow
from ...core.workflow.experiment import ExperimentFlow
from ...core.workflow.review import ReviewFlow
from ...core.workflow.write import WriteFlow
from ...core.model import get_model_config
from ...core.storage import StorageManager
from ..models import (
    RunWorkflowRequest,
    SSEMessage,
    WorkflowName,
    WorkflowRunSummary,
)
from ..sse.events import (
    emit_log,
    emit_step_completed,
    emit_workflow_finished,
    emit_workflow_started,
)

router = APIRouter()

# In-memory run registry (in MVP). In V2, use persistent StorageManager.
RUNS: Dict[str, Dict[str, Any]] = {}

# Workflow class mapping
WORKFLOW_CLASSES = {
    WorkflowName.IDEA: IdeaFlow,
    WorkflowName.EXPERIMENT: ExperimentFlow,
    WorkflowName.REVIEW: ReviewFlow,
    WorkflowName.WRITE: WriteFlow,
}


@router.post("/{workflow_name}/run")
async def run_workflow(
    workflow_name: WorkflowName,
    request: RunWorkflowRequest,
    req: Request,
):
    """Start a new workflow run."""
    if workflow_name not in WORKFLOW_CLASSES:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_name} not found")

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    # Initialize run registry entry
    RUNS[run_id] = {
        "run_id": run_id,
        "workflow_name": workflow_name.value,
        "status": WorkflowStatus.RUNNING,
        "started_at": started_at,
        "current_step": None,
        "logs": [],
        "error": None,
    }

    # Emit started event
    await emit_workflow_started(run_id, workflow_name.value, started_at)
    await emit_log(run_id, "info", f"Starting {workflow_name.value} workflow (run_id={run_id})")

    # Launch workflow execution in background (non-blocking)
    # In a real deployment, this would be a background task or Celery
    # Here we spawn async task immediately and return run_id
    asyncio_task = asyncio.create_task(
        execute_workflow(
            run_id=run_id,
            workflow_name=workflow_name,
            params=request.parameters,
        )
    )
    # Optional: attach to request state to prevent GC; but for demo, background is fine.

    return {"run_id": run_id, "status": "started"}


@router.get("/{run_id}")
async def get_workflow_status(run_id: str) -> WorkflowRunSummary:
    """Get current status of a workflow run."""
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="Run not found")

    run = RUNS[run_id]
    return WorkflowRunSummary(
        run_id=run["run_id"],
        workflow_name=run["workflow_name"],
        status=run["status"],
        started_at=run["started_at"],
        completed_at=run.get("completed_at"),
        current_step=run.get("current_step"),
        error=run.get("error"),
    )


async def execute_workflow(run_id: str, workflow_name: WorkflowName, params: Dict[str, Any]):
    """Execute workflow logic with event emissions."""
    try:
        # Get model config and storage
        model_cfg = get_model_config()
        storage = StorageManager()

        # Instantiate the workflow
        WorkflowCls = WORKFLOW_CLASSES[workflow_name]
        workflow = WorkflowCls(model_config=model_cfg, storage=storage, **params)

        await emit_log(run_id, "info", "Executing workflow...")

        # Run in thread executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, workflow.run)

        # Mark completed
        RUNS[run_id]["status"] = WorkflowStatus.COMPLETED
        RUNS[run_id]["completed_at"] = datetime.now(timezone.utc)
        await emit_log(run_id, "info", "Workflow completed successfully")
        await emit_workflow_finished(run_id, WorkflowStatus.COMPLETED, final_output=result)

    except Exception as e:
        RUNS[run_id]["status"] = WorkflowStatus.FAILED
        RUNS[run_id]["error"] = str(e)
        await emit_log(run_id, "error", f"Workflow failed: {e}")
        await emit_workflow_finished(run_id, WorkflowStatus.FAILED, error=str(e))
