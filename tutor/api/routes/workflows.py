"""Workflow API Routes

提供工作流执行和管理端点：
- POST /api/v1/workflows/run - 启动工作流
- GET /api/v1/workflows - 列出所有运行
- GET /api/v1/workflows/{run_id} - 获取运行状态
- DELETE /api/v1/workflows/{run_id} - 删除运行
- POST /api/v1/workflows/{run_id}/retry - 重试运行
- POST /api/v1/workflows/{run_id}/cancel - 取消运行
- PATCH /api/v1/workflows/{run_id}/tags - 更新标签
- POST /api/v1/workflows/batch-delete - 批量删除
- DELETE /api/v1/workflows/cleanup - 清理旧运行
- GET /api/v1/workflows/stats - 获取统计信息
- GET /api/v1/workflows/list/archived - 列出已归档
- GET /api/v1/workflows/list/favorites - 列出收藏
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tutor.api.main import WorkflowType, RunRequest, RunResponse, RunStatusResponse, BatchDeleteRequest
from tutor.api.models import success_response, paginated_response
from tutor.core.storage.workflow_runs import RunStorage
from tutor.core.workflow.base import WorkflowEngine
from tutor.core.workflow.approval import approval_manager as am
from tutor.api.main import broadcaster

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])

# 依赖注入
def get_run_storage() -> RunStorage:
    """获取运行存储实例"""
    return RunStorage()


@router.post("/run")
async def start_run(request: RunRequest):
    """启动工作流执行

    支持的工作流类型：
    - idea: 创意生成
    - experiment: 实验执行
    - review: 论文评审
    - write: 论文撰写
    """
    from tutor.api.models import success_response
    
    valid_types = WorkflowType.all()
    if request.workflow_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workflow_type '{request.workflow_type}'. Must be one of: {valid_types}",
        )

    run_id = str(uuid.uuid4())
    run_storage = get_run_storage()
    run_storage.create_run(
        run_id=run_id,
        workflow_type=request.workflow_type,
        params=request.params,
        config=request.config,
    )

    # Fire and forget — run workflow in background
    asyncio.create_task(
        _execute_workflow(run_id, request, run_storage, broadcaster)
    )

    return success_response(data=RunResponse(
        run_id=run_id,
        status="pending",
        workflow_type=request.workflow_type,
        message=f"Workflow '{request.workflow_type}' started. Run ID: {run_id}",
    ))


@router.get("")
async def list_runs(
    status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """列出所有运行记录"""
    run_storage = get_run_storage()
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


@router.get("/stats")
async def get_stats():
    """获取工作流运行统计"""
    run_storage = get_run_storage()
    stats = run_storage.get_stats()
    return success_response(data=stats)


@router.get("/list/archived")
async def list_archived_runs(limit: int = 100, offset: int = 0):
    """列出已归档的工作流"""
    run_storage = get_run_storage()
    runs = run_storage.list_runs_by_tags(
        ["archived"], match_all=False, limit=limit, offset=offset
    )
    return paginated_response(
        items=runs, total=len(runs), limit=limit, offset=offset
    )


@router.get("/list/favorites")
async def list_favorite_runs(limit: int = 100, offset: int = 0):
    """列出收藏的工作流"""
    run_storage = get_run_storage()
    runs = run_storage.list_runs_by_tags(
        ["favorite"], match_all=False, limit=limit, offset=offset
    )
    return paginated_response(
        items=runs, total=len(runs), limit=limit, offset=offset
    )


@router.post("/batch-delete")
async def batch_delete_runs(request: BatchDeleteRequest):
    """批量删除工作流

    Body: {"run_ids": ["id1", "id2", ...]}
    """
    if not request.run_ids:
        raise HTTPException(status_code=400, detail="run_ids is required")
    run_storage = get_run_storage()
    deleted = []
    failed = []
    for run_id in request.run_ids:
        success = run_storage.delete_run(run_id)
        if success:
            deleted.append(run_id)
        else:
            failed.append(run_id)
    return success_response(
        data={"deleted": deleted, "failed": failed, "total": len(request.run_ids)}
    )


@router.delete("/cleanup")
async def cleanup_old_runs(
    status: Optional[str] = None,
    older_than_days: int = 7,
    dry_run: bool = False,
):
    """清理旧工作流

    Query params:
    - status: 筛选状态 (completed, failed)
    - older_than_days: 清理多少天前的数据 (默认7天)
    - dry_run: 是否只返回数量不实际删除
    """
    run_storage = get_run_storage()
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    cutoff_str = cutoff.isoformat()

    # 使用 SQL 查询直接获取符合条件的 run_ids，避免加载全部数据到内存
    conn = run_storage._get_conn()
    cursor = conn.cursor()

    if status:
        cursor.execute(
            "SELECT run_id FROM workflow_runs WHERE status = ? AND updated_at < ? ORDER BY updated_at ASC",
            (status, cutoff_str),
        )
    else:
        cursor.execute(
            "SELECT run_id FROM workflow_runs WHERE status IN ('completed', 'failed') AND updated_at < ? ORDER BY updated_at ASC",
            (cutoff_str,),
        )

    to_delete = [row["run_id"] for row in cursor.fetchall()]

    if dry_run:
        return success_response(
            data={
                "count": len(to_delete),
                "run_ids": to_delete[:50],
                "message": f"Found {len(to_delete)} runs older than {older_than_days} days",
            }
        )

    deleted = []
    for run_id in to_delete:
        if run_storage.delete_run(run_id):
            deleted.append(run_id)

    return success_response(
        data={
            "deleted": len(deleted),
            "total_found": len(to_delete),
            "older_than_days": older_than_days,
        }
    )


# ==================== Approval Routes ====================

@router.get("/approvals")
async def list_approvals(
    run_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """List approval requests"""
    results = am.list_all(run_id=run_id, status=status)
    return success_response(data={
        "total": len(results),
        "approvals": [r.to_dict() for r in results],
    })


@router.get("/approvals/pending")
async def list_pending_approvals(run_id: Optional[str] = None):
    """List pending approvals"""
    results = am.list_pending(run_id=run_id)
    return success_response(data={
        "total": len(results),
        "approvals": [r.to_dict() for r in results],
    })


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str):
    """Get approval details"""
    request = am.get_request(approval_id)
    if not request:
        raise HTTPException(
            status_code=404, detail=f"Approval '{approval_id}' not found"
        )
    return success_response(data=request.to_dict())


@router.post("/approvals/{approval_id}/approve")
async def approve_request(approval_id: str, comment: Optional[str] = ""):
    """Approve an approval request and resume the associated workflow"""
    success = am.approve(approval_id, comment=comment or "")
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve '{approval_id}'. Not found or already resolved.",
        )

    # Trigger workflow resume
    request = am.get_request(approval_id)
    if request and request.run_id:
        # Try to find and resume the paused workflow
        run_storage = get_run_storage()
        run = run_storage.get_run(request.run_id)
        if run and run.get("status") == "paused":
            # Import here to avoid circular imports
            engine = WorkflowEngine()
            # Resume in background
            asyncio.create_task(
                _resume_workflow_async(request.run_id, engine, None, None)
            )

    return success_response(data=request.to_dict())


@router.post("/approvals/{approval_id}/reject")
async def reject_request(approval_id: str, comment: Optional[str] = ""):
    """Reject an approval request"""
    success = am.reject(approval_id, comment=comment or "")
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject '{approval_id}'. Not found or already resolved.",
        )
    request = am.get_request(approval_id)
    return success_response(data=request.to_dict())


@router.post("/approvals/{approval_id}/cancel")
async def cancel_request(approval_id: str):
    """Cancel an approval request"""
    success = am.cancel(approval_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Approval '{approval_id}' not found"
        )
    return success_response(data={"status": "cancelled", "approval_id": approval_id})


# ==================== Run-specific Routes ====================

@router.get("/{run_id}")
async def get_run_status(run_id: str):
    """查询运行状态"""
    run_storage = get_run_storage()
    run = run_storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return success_response(data=RunStatusResponse(**run).model_dump())


@router.delete("/{run_id}")
async def delete_run(run_id: str):
    """删除工作流运行记录"""
    run_storage = get_run_storage()
    success = run_storage.delete_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return success_response(data={"run_id": run_id, "status": "deleted"})


@router.post("/{run_id}/retry")
async def retry_run(run_id: str):
    """重试失败的工作流，使用相同的参数创建新的运行"""
    run_storage = get_run_storage()
    original_run = run_storage.get_run(run_id)
    if not original_run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if original_run.get("status") not in ("failed", "completed", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Only failed/completed/paused runs can be retried. Current status: {original_run.get('status')}",
        )

    # 创建新的运行，使用原始参数
    new_run_id = str(uuid.uuid4())
    run_storage.create_run(
        run_id=new_run_id,
        workflow_type=original_run.get("workflow_type"),
        params=original_run.get("params", {}),
        config=original_run.get("config", {}),
    )

    # 启动工作流
    asyncio.create_task(
        _execute_workflow(
            new_run_id,
            RunRequest(
                workflow_type=original_run.get("workflow_type"),
                params=original_run.get("params", {}),
                config=original_run.get("config", {}),
            ),
            run_storage,
            broadcaster,
        )
    )

    return success_response(
        data={
            "original_run_id": run_id,
            "new_run_id": new_run_id,
            "message": f"Workflow retry started. New Run ID: {new_run_id}",
        }
    )


@router.patch("/{run_id}/tags")
async def update_run_tags(run_id: str, tags: Dict[str, Any]):
    """更新工作流标签（用于归档、收藏等）

    Body: {"tags": ["archived", "favorite"]}
    """
    run_storage = get_run_storage()
    run = run_storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    tags_list = tags.get("tags", [])
    if not isinstance(tags_list, list):
        raise HTTPException(status_code=400, detail="tags must be a list")

    success = run_storage.update_tags(run_id, tags_list)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update tags")

    # 返回更新后的记录
    updated_run = run_storage.get_run(run_id)
    return success_response(data=updated_run)


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str):
    """取消运行中的工作流

    1. 更新数据库状态为 cancelled
    2. 发送取消信号到正在运行的 asyncio task
    3. 发送 SSE 取消事件通知前端
    """
    run_storage = get_run_storage()
    run = run_storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if run["status"] not in ["pending", "running"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel run in status '{run['status']}'"
        )

    run_storage.update_status(run_id, "cancelled")

    # 发送取消信号到正在运行的工作流
    broadcaster.signal_cancel(run_id)

    # 通知 SSE 订阅者
    await broadcaster.emit(
        run_id, "cancelled", {"message": "Run cancelled by user"}
    )

    return success_response(
        data={
            "status": "cancelled",
            "run_id": run_id,
        }
    )


# ==================== Helper Functions ====================

# Workflow class mapping (module-level for efficiency)
_WORKFLOW_CLASSES = {}


def _load_workflow_classes():
    """Lazy-load workflow classes once."""
    global _WORKFLOW_CLASSES
    if not _WORKFLOW_CLASSES:
        try:
            from tutor.core.workflow.idea import IdeaFlow

            _WORKFLOW_CLASSES[WorkflowType.IDEA] = IdeaFlow
            from tutor.core.workflow.experiment import ExperimentFlow

            _WORKFLOW_CLASSES[WorkflowType.EXPERIMENT] = ExperimentFlow
            from tutor.core.workflow.review import ReviewFlow

            _WORKFLOW_CLASSES[WorkflowType.REVIEW] = ReviewFlow
            from tutor.core.workflow.write import WriteFlow

            _WORKFLOW_CLASSES[WorkflowType.WRITE] = WriteFlow
        except ImportError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Some workflow classes not available: {e}")


async def _execute_workflow(
    run_id: str,
    request: RunRequest,
    run_storage: "RunStorage",
    broadcaster: "EventBroadcaster",
):
    """后台执行工作流"""
    try:
        from tutor.core.workflow.base import (
            WorkflowEngine,
            register_workflow_engine,
            unregister_workflow_engine,
        )
        from tutor.core.model import ModelGateway
        from pathlib import Path
        import os

        _load_workflow_classes()

        # 1. 环境准备
        storage_path = Path(os.getcwd()) / "test_results"
        storage_path.mkdir(parents=True, exist_ok=True)

        # 2. 初始化引擎（注入广播器）
        gateway = ModelGateway(request.config or {})
        engine = WorkflowEngine(storage_path, gateway, broadcaster=broadcaster)

        # 注册引擎到全局注册表（支持暂停后恢复）
        register_workflow_engine(run_id, engine)

        workflow_class = _WORKFLOW_CLASSES.get(request.workflow_type)
        if not workflow_class:
            raise ValueError(f"Unsupported workflow type: {request.workflow_type}")

        # 4. 创建并运行
        run_storage.update_status(run_id, "running")
        await broadcaster.emit(run_id, "started", {"run_id": run_id})

        workflow = engine.create_workflow(workflow_class, run_id, request.params)

        # 使用后台任务运行，支持取消
        task = asyncio.create_task(asyncio.to_thread(engine.run_workflow, run_id))

        # 等待任务完成或被取消
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            # 工作流被取消，等待任务实际停止
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            run_storage.update_status(run_id, "cancelled")
            await broadcaster.emit(
                run_id, "cancelled", {"message": "Run cancelled by user"}
            )
            return

        # 5. 获取费用信息
        usage_summary = gateway.get_usage_summary()
        
        # 6. 更新状态，包含费用信息
        run_storage.update_status(
            run_id,
            result.status,
            result=result.output,
            error=result.error,
            usage=usage_summary
        )

        # 7. 发送完成事件，包含费用信息
        complete_data = result.to_dict()
        complete_data['usage'] = usage_summary
        await broadcaster.emit_complete(run_id, complete_data)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Workflow {run_id} failed: {e}", exc_info=True)
        run_storage.update_status(run_id, "failed", error=str(e))
        await broadcaster.emit(run_id, "error", {"message": str(e)})
        await broadcaster.unsubscribe(run_id)
    finally:
        # 清理注册
        from tutor.core.workflow.base import unregister_workflow_engine
        unregister_workflow_engine(run_id)


async def _resume_workflow_async(run_id, engine, *args, **kwargs):
    """异步恢复工作流"""
    try:
        # 这里可以实现工作流恢复逻辑
        pass
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to resume workflow {run_id}: {e}")
