"""Legacy API endpoints (deprecated).

These endpoints are maintained for backward compatibility but are deprecated.
New code should use the /api/v1/* endpoints instead.
"""

import asyncio
import uuid
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from tutor.api.main import (
    RunRequest,
    RunResponse,
    RunStatusResponse,
    WorkflowType,
    _execute_workflow,
)
from tutor.api.models import (
    error_response,
    paginated_response,
    success_response,
)

router = APIRouter(tags=["legacy"])


def get_run_storage():
    """Dependency to get run storage instance."""
    from tutor.core.storage.workflow_runs import RunStorage
    return RunStorage()


def get_broadcaster():
    """Dependency to get event broadcaster instance."""
    from tutor.api.main import broadcaster
    return broadcaster


@router.post("/run", response_model=RunResponse, deprecated=True)
async def start_run_legacy(
    request: RunRequest,
    run_storage = Depends(get_run_storage),
    broadcaster = Depends(get_broadcaster),
):
    """Start a workflow run (deprecated, use POST /api/v1/workflows instead)."""
    warnings.warn(
        "Legacy /run endpoint is deprecated. Use POST /api/v1/workflows instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    valid_types = WorkflowType.all()
    if request.workflow_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workflow_type '{request.workflow_type}'. Must be one of: {valid_types}",
        )

    run_id = str(uuid.uuid4())
    run_storage.create_run(
        run_id=run_id,
        workflow_type=request.workflow_type,
        params=request.params,
        config=request.config,
    )
    asyncio.create_task(
        _execute_workflow(run_id, request, run_storage, broadcaster)
    )
    return RunResponse(
        run_id=run_id,
        status="pending",
        workflow_type=request.workflow_type,
        message=f"Workflow '{request.workflow_type}' started. Run ID: {run_id}",
    )


@router.get("/runs/{run_id}", deprecated=True)
async def get_run_legacy(run_id: str, run_storage = Depends(get_run_storage)):
    """Get run status (deprecated, use GET /api/v1/workflows/{run_id} instead)."""
    warnings.warn(
        "Legacy /runs/{run_id} endpoint is deprecated. Use GET /api/v1/workflows/{run_id} instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    run = run_storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return success_response(data=RunStatusResponse(**run).model_dump())


@router.get("/runs", deprecated=True)
async def list_runs_legacy(
    run_storage = Depends(get_run_storage),
    status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List runs (deprecated, use GET /api/v1/workflows instead)."""
    warnings.warn(
        "Legacy /runs endpoint is deprecated. Use GET /api/v1/workflows instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    result = run_storage.list_runs(
        status=status,
        workflow_type=workflow_type,
        limit=limit,
        offset=offset,
    )
    return paginated_response(
        items=result.get("runs", []),
        total=result.get("total", 0),
        limit=limit,
        offset=offset,
    )


@router.get("/stats", deprecated=True)
async def get_stats_legacy(run_storage = Depends(get_run_storage)):
    """Get statistics (deprecated, use GET /api/v1/workflows/stats instead)."""
    warnings.warn(
        "Legacy /stats endpoint is deprecated. Use GET /api/v1/workflows/stats instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    return success_response(data=run_storage.get_stats())


@router.delete("/runs/{run_id}", deprecated=True)
async def delete_run_legacy(run_id: str, run_storage = Depends(get_run_storage)):
    """Delete a run (deprecated, use DELETE /api/v1/workflows/{run_id} instead)."""
    warnings.warn(
        "Legacy /runs/{run_id} DELETE endpoint is deprecated. Use DELETE /api/v1/workflows/{run_id} instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    success = run_storage.delete_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return success_response(data={"run_id": run_id, "status": "deleted"})


@router.post("/runs/{run_id}/cancel", deprecated=True)
async def cancel_run_legacy(
    run_id: str,
    run_storage = Depends(get_run_storage),
    broadcaster = Depends(get_broadcaster),
):
    """Cancel a run (deprecated, use POST /api/v1/workflows/{run_id}/cancel instead)."""
    warnings.warn(
        "Legacy /runs/{run_id}/cancel endpoint is deprecated. Use POST /api/v1/workflows/{run_id}/cancel instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    run = run_storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if run["status"] not in ["pending", "running"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel run in status '{run['status']}'"
        )
    broadcaster.signal_cancel(run_id)
    run_storage.update_status(run_id, "cancelled")
    return success_response(data={"run_id": run_id, "cancelled": True})


@router.get("/approvals", deprecated=True)
async def list_approvals_legacy():
    """List approvals (deprecated)."""
    warnings.warn(
        "Legacy /approvals endpoint is deprecated.",
        DeprecationWarning,
        stacklevel=2,
    )

    from tutor.core.workflow.approval import approval_manager as am
    approvals = [req.to_dict() for req in am.list_all()]
    return {"total": len(approvals), "approvals": approvals}


@router.get("/approvals/pending", deprecated=True)
async def list_pending_approvals_legacy():
    """List pending approvals (deprecated)."""
    from tutor.core.workflow.approval import approval_manager as am
    approvals = [req.to_dict() for req in am.list_pending()]
    return {"total": len(approvals), "approvals": approvals}


@router.get("/approvals/{approval_id}", deprecated=True)
async def get_approval_legacy(approval_id: str):
    """Get approval (deprecated)."""
    from tutor.core.workflow.approval import approval_manager as am
    req = am.get_request(approval_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval not found")
    return req.to_dict()


@router.post("/approvals/{approval_id}/approve", deprecated=True)
async def approve_approval_legacy(approval_id: str):
    """Approve request (deprecated)."""
    from tutor.core.workflow.approval import approval_manager as am
    ok = am.approve(approval_id, by="user", comment="")
    if not ok:
        raise HTTPException(
            status_code=400, detail="Approval not found or not pending"
        )
    return {"status": "approved", "approval_id": approval_id}


@router.post("/approvals/{approval_id}/reject", deprecated=True)
async def reject_approval_legacy(approval_id: str):
    """Reject approval (deprecated)."""
    from tutor.core.workflow.approval import approval_manager as am
    ok = am.reject(approval_id, by="user", comment="")
    if not ok:
        raise HTTPException(
            status_code=400, detail="Approval not found or not pending"
        )
    return {"status": "rejected", "approval_id": approval_id}
