"""TUTOR Web API 主应用

FastAPI应用，提供：
- RESTful 工作流执行接口
- Server-Sent Events (SSE) 实时进度推送
- 健康检查与OpenAPI文档
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from fastapi import HTTPException, FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse
except ImportError:
    HTTPException = Exception
    JSONResponse = None
    StreamingResponse = None
    Fast = None

from tutor.api.models import (
    success_response,
    error_response,
    paginated_response,
)

logger = logging.getLogger(__name__)


class WorkflowType:
    """工作流类型常量"""

    IDEA = "idea"
    EXPERIMENT = "experiment"
    REVIEW = "review"
    WRITE = "write"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.IDEA, cls.EXPERIMENT, cls.REVIEW, cls.WRITE]

    @classmethod
    def is_valid(cls, workflow_type: str) -> bool:
        return workflow_type in cls.all()


class RateLimiter:
    """简单的内存限流器

    生产环境建议使用 Redis 分布式限流
    """

    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup: float = time.time()

    def _cleanup_old_entries(self) -> None:
        """定期清理不再活跃的客户端条目"""
        now = time.time()
        # 每5分钟清理一次
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        minute_ago = now - 60
        inactive_clients = [
            cid
            for cid, timestamps in self.requests.items()
            if not timestamps or max(timestamps) < minute_ago
        ]
        for cid in inactive_clients:
            del self.requests[cid]

    def is_allowed(self, client_id: str) -> bool:
        """检查请求是否允许"""
        now = time.time()
        minute_ago = now - 60

        # 清理旧请求
        self.requests[client_id] = [
            t for t in self.requests[client_id] if t > minute_ago
        ]

        # 检查限流
        if len(self.requests[client_id]) >= self.requests_per_minute:
            return False

        # 记录请求
        self.requests[client_id].append(now)

        # 定期清理不活跃客户端
        self._cleanup_old_entries()
        return True

    def get_retry_after(self, client_id: str) -> int:
        """获取需要等待的秒数"""
        if client_id not in self.requests[client_id]:
            return 0

        now = time.time()
        oldest = min(self.requests[client_id])
        wait_time = 60 - (now - oldest)
        return max(1, int(wait_time))


# 全局限流器
rate_limiter = RateLimiter(requests_per_minute=60, burst_size=10)


async def rate_limit_middleware(request: Request, call_next):
    """限流中间件"""
    # 跳过健康检查端点
    if request.url.path in ["/health", "/health/live", "/health/ready", "/metrics"]:
        return await call_next(request)

    # 获取客户端标识
    client_id = request.client.host if request.client else "unknown"

    # 检查限流
    if not rate_limiter.is_allowed(client_id):
        retry_after = rate_limiter.get_retry_after(client_id)
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too many requests",
                "detail": f"Rate limit exceeded. Retry after {retry_after} seconds.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    response = await call_next(request)
    return response


async def api_key_auth_middleware(request: Request, call_next):
    """API Key authentication middleware.

    Protects all non-health endpoints with X-API-Key header validation.
    Skip auth for: /health/*, /metrics, /docs, /openapi.json
    """
    # Paths that don't require authentication
    public_paths = {
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/metrics/json",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
    }

    # Public paths that start with these prefixes (no auth required)
    public_prefixes = []

    if request.url.path in public_paths or request.url.path.startswith("/docs"):
        return await call_next(request)

    # Check public prefixes
    for prefix in public_prefixes:
        if request.url.path.startswith(prefix):
            return await call_next(request)

    # Check for API key header
    api_key = request.headers.get("X-API-Key")
    expected_key = os.environ.get("API_KEY", "")

    # If no API_KEY configured, skip auth (dev mode)
    if not expected_key:
        return await call_next(request)

    # Validate API key
    if not api_key or api_key != expected_key:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "detail": "Missing or invalid X-API-Key header",
            },
        )

    response = await call_next(request)
    return response


class EventBroadcaster:
    """SSE事件广播器

    管理运行中的workflow事件流，支持多客户端订阅。
    """

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._cancel_events: Dict[str, asyncio.Event] = {}

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        """订阅指定run的事件流"""
        queue = asyncio.Queue(maxsize=100)
        if run_id not in self._subscribers:
            self._subscribers[run_id] = []
        self._subscribers[run_id].append(queue)
        logger.debug(
            f"SSE subscriber added for run {run_id} (total: {len(self._subscribers[run_id])})"
        )
        return queue

    async def unsubscribe(
        self, run_id: str, queue: Optional[asyncio.Queue] = None
    ) -> None:
        """取消订阅"""
        if run_id not in self._subscribers:
            return
        if queue:
            self._subscribers[run_id] = [
                q for q in self._subscribers[run_id] if q is not queue
            ]
        else:
            self._subscribers[run_id] = []
        if not self._subscribers[run_id]:
            del self._subscribers[run_id]
        logger.debug(f"SSE subscriber removed for run {run_id}")

    async def emit(self, run_id: str, event_type: str, data: Any) -> None:
        """发送事件到所有订阅者"""
        queues = self._subscribers.get(run_id, [])
        if queues:
            event = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            }
            dead_queues = []
            for queue in queues:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"Event queue full for run {run_id}, dropping event")
                except Exception:
                    dead_queues.append(queue)
            for dead in dead_queues:
                if dead in queues:
                    queues.remove(dead)

    async def emit_complete(self, run_id: str, result: Any) -> None:
        """发送完成事件并关闭队列"""
        await self.emit(run_id, "complete", result)
        await self.unsubscribe(run_id)
        self._cancel_events.pop(run_id, None)

    def signal_cancel(self, run_id: str) -> None:
        """发送取消信号给正在运行的工作流"""
        if run_id not in self._cancel_events:
            self._cancel_events[run_id] = asyncio.Event()
        self._cancel_events[run_id].set()
        logger.info(f"Cancel signal sent for run {run_id}")

    def is_cancelled(self, run_id: str) -> bool:
        """检查工作流是否已被取消"""
        event = self._cancel_events.get(run_id)
        return event.is_set() if event else False


# 全局广播器单例
broadcaster = EventBroadcaster()


# --- Pydantic Models ---

try:
    from pydantic import BaseModel, Field
except ImportError:

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def Field(default=None, **kwargs):
        return default


class RunRequest(BaseModel):
    """工作流执行请求"""

    workflow_type: str = Field(
        ..., description="工作流类型: idea/experiment/review/write"
    )
    params: Dict[str, Any] = Field(default_factory=dict, description="工作流参数")
    config: Optional[Dict[str, Any]] = Field(default=None, description="运行配置覆盖")


class RunResponse(BaseModel):
    """工作流执行响应"""

    run_id: str
    status: str
    workflow_type: str
    message: str


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""

    run_ids: List[str] = Field(default_factory=list, description="要删除的运行ID列表")


class RunStatusResponse(BaseModel):
    """运行状态查询响应"""

    run_id: str
    status: str
    workflow_type: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """错误响应"""

    error: str
    detail: Optional[str] = None


# --- Application Factory ---


def create_app() -> "FastAPI":
    """创建FastAPI应用"""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        logger.error("FastAPI not installed. Install with: pip install fastapi uvicorn")
        raise

    app = FastAPI(
        title="TUTOR API",
        description="TUTOR智能研究自动化平台 Web API",
        version="0.2.0",
    )

    # 添加中间件
    allowed_origins = os.environ.get(
        "TUTOR_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # 注册限流中间件
    app.middleware("http")(rate_limit_middleware)

    # 注册API密钥认证中间件
    app.middleware("http")(api_key_auth_middleware)

    # --- Database storage ---
    from tutor.core.storage.workflow_runs import RunStorage

    run_storage = RunStorage()

    # --- Routes ---

    @app.get("/health", tags=["system"])
    async def health_check():
        """健康检查（兼容性）"""
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

    @app.get("/health/live", tags=["system"])
    async def health_live():
        """Liveness Probe - 应用是否存活"""
        return {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

    @app.get("/health/ready", tags=["system"])
    async def health_ready():
        """Readiness Probe - 应用是否就绪（依赖检查）"""
        checks = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

        # 检查磁盘空间
        try:
            import shutil
            from pathlib import Path

            storage_path = Path.cwd()
            usage = shutil.disk_usage(storage_path)
            checks["disk_ok"] = usage.percent < 95
            checks["disk_usage_percent"] = round(usage.percent, 2)
        except Exception as e:
            checks["disk_ok"] = False
            checks["disk_error"] = str(e)

        # 检查配置
        checks["config_loaded"] = True

        # 检查限流器
        checks["rate_limiter_ok"] = True

        # 总体就绪状态
        is_ready = checks.get("disk_ok", False) and checks.get("config_loaded", False)
        checks["status"] = "ready" if is_ready else "not_ready"

        status_code = 200 if is_ready else 503
        return JSONResponse(content=checks, status_code=status_code)

    @app.get("/metrics", tags=["system"])
    async def prometheus_metrics():
        """Prometheus metrics endpoint"""
        from tutor.api.prometheus import get_metrics

        metrics = get_metrics()
        return StreamingResponse(
            iter([metrics.format_prometheus()]), media_type="text/plain"
        )

    @app.post("/run", response_model=RunResponse, tags=["workflow"])
    async def start_run(request: RunRequest):
        """启动工作流执行

        支持的工作流类型：
        - idea: 创意生成
        - experiment: 实验执行
        - review: 论文评审
        - write: 论文撰写
        """
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

        # Fire and forget — run workflow in background
        asyncio.create_task(
            _execute_workflow(run_id, request, run_storage, broadcaster)
        )

        return RunResponse(
            run_id=run_id,
            status="pending",
            workflow_type=request.workflow_type,
            message=f"Workflow '{request.workflow_type}' started. Run ID: {run_id}",
        )

    @app.get("/runs/{run_id}", tags=["workflow"])
    async def get_run_status(run_id: str):
        """查询运行状态"""
        run = run_storage.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return success_response(data=RunStatusResponse(**run).model_dump())

    @app.get("/runs", tags=["workflow"])
    async def list_runs(
        status: Optional[str] = None,
        workflow_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        """列出所有运行记录"""
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

    @app.get("/stats", tags=["workflow"])
    async def get_stats():
        """获取工作流运行统计"""
        stats = run_storage.get_stats()
        return success_response(data=stats)

    # 注意：这些特定路径必须在 /runs/{run_id} 之前定义，否则会被当作 run_id
    @app.get("/runs/list/archived", tags=["workflow"])
    async def list_archived_runs(limit: int = 100, offset: int = 0):
        """列出已归档的工作流"""
        runs = run_storage.list_runs_by_tags(
            ["archived"], match_all=False, limit=limit, offset=offset
        )
        return paginated_response(
            items=runs, total=len(runs), limit=limit, offset=offset
        )

    @app.get("/runs/list/favorites", tags=["workflow"])
    async def list_favorite_runs(limit: int = 100, offset: int = 0):
        """列出收藏的工作流"""
        runs = run_storage.list_runs_by_tags(
            ["favorite"], match_all=False, limit=limit, offset=offset
        )
        return paginated_response(
            items=runs, total=len(runs), limit=limit, offset=offset
        )

    @app.delete("/runs/{run_id}", tags=["workflow"])
    async def delete_run(run_id: str):
        """删除工作流运行记录"""
        success = run_storage.delete_run(run_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return success_response(data={"run_id": run_id, "status": "deleted"})

    @app.post("/runs/{run_id}/retry", tags=["workflow"])
    async def retry_run(run_id: str):
        """重试失败的工作流，使用相同的参数创建新的运行"""
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

    @app.post("/runs/batch-delete", tags=["workflow"])
    async def batch_delete_runs(request: BatchDeleteRequest):
        """批量删除工作流

        Body: {"run_ids": ["id1", "id2", ...]}
        """
        if not request.run_ids:
            raise HTTPException(status_code=400, detail="run_ids is required")
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

    @app.delete("/runs/cleanup", tags=["workflow"])
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
        from datetime import datetime, timedelta, timezone

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

    @app.patch("/runs/{run_id}/tags", tags=["workflow"])
    async def update_run_tags(run_id: str, tags: Dict[str, Any]):
        """更新工作流标签（用于归档、收藏等）

        Body: {"tags": ["archived", "favorite"]}
        """
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

    @app.post("/runs/{run_id}/cancel", tags=["workflow"])
    async def cancel_run(run_id: str):
        """取消运行中的工作流

        1. 更新数据库状态为 cancelled
        2. 发送取消信号到正在运行的 asyncio task
        3. 发送 SSE 取消事件通知前端
        """
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

        return {"status": "cancelled", "run_id": run_id}

    @app.get("/events/{run_id}", tags=["events"])
    async def event_stream(run_id: str):
        """SSE事件流 — 实时推送工作流进度

        事件类型：
        - started: 工作流开始
        - step: 步骤进度更新
        - llm_call: LLM调用记录（模型/token/延迟）
        - checkpoint: 检查点保存
        - complete: 工作流完成
        - error: 错误事件
        """
        from fastapi.responses import StreamingResponse

        run = run_storage.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        async def generate():
            queue = await broadcaster.subscribe(run_id)
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30)
                        yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                        if event["type"] in ("complete", "error"):
                            break
                    except asyncio.TimeoutError:
                        yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.now(timezone.utc).isoformat() + 'Z'})}\n\n"
            finally:
                await broadcaster.unsubscribe(run_id, queue)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ==================== Approval Routes ====================

    # Import once at module level for efficiency
    from tutor.core.workflow.approval import approval_manager as am

    @app.get("/approvals", tags=["approvals"])
    async def list_approvals(
        run_id: Optional[str] = None,
        status: Optional[str] = None,
    ):
        """List approval requests"""
        results = am.list_all(run_id=run_id, status=status)
        return {
            "total": len(results),
            "approvals": [r.to_dict() for r in results],
        }

    @app.get("/approvals/pending", tags=["approvals"])
    async def list_pending_approvals(run_id: Optional[str] = None):
        """List pending approvals"""
        results = am.list_pending(run_id=run_id)
        return {
            "total": len(results),
            "approvals": [r.to_dict() for r in results],
        }

    @app.get("/approvals/{approval_id}", tags=["approvals"])
    async def get_approval(approval_id: str):
        """Get approval details"""
        request = am.get_request(approval_id)
        if not request:
            raise HTTPException(
                status_code=404, detail=f"Approval '{approval_id}' not found"
            )
        return request.to_dict()

    @app.post("/approvals/{approval_id}/approve", tags=["approvals"])
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
            run = run_storage.get_run(request.run_id)
            if run and run.get("status") == "paused":
                # Import here to avoid circular imports
                from tutor.core.workflow.engine import WorkflowEngine

                engine = WorkflowEngine()
                # Resume in background
                asyncio.create_task(
                    _resume_workflow_async(request.run_id, engine, None, None)
                )

        return request.to_dict()

    @app.post("/approvals/{approval_id}/reject", tags=["approvals"])
    async def reject_request(approval_id: str, comment: Optional[str] = ""):
        """Reject an approval request"""
        success = am.reject(approval_id, comment=comment or "")
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reject '{approval_id}'. Not found or already resolved.",
            )
        request = am.get_request(approval_id)
        return request.to_dict()

    @app.post("/approvals/{approval_id}/cancel", tags=["approvals"])
    async def cancel_request(approval_id: str):
        """Cancel an approval request"""
        success = am.cancel(approval_id)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Approval '{approval_id}' not found"
            )
        return {"status": "cancelled", "approval_id": approval_id}

    # --- Auth Routes ---
    # 用户认证端点（无需API Key认证）
    from tutor.api.routes.auth import router as auth_router

    app.include_router(auth_router)

    # 用户管理端点（无需API Key认证）
    from tutor.api.routes.users import router as users_router

    app.include_router(users_router)

    # Provider 配置端点
    from tutor.api.routes.providers import router as providers_router

    app.include_router(providers_router)

    # Project 项目管理端点
    from tutor.api.routes.projects import router as projects_router

    app.include_router(projects_router)

    # File Upload 端点
    from tutor.api.routes.uploads import router as uploads_router

    app.include_router(uploads_router)

    return app


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
            logger.warning(f"Some workflow classes not available: {e}")


async def _execute_workflow(
    run_id: str,
    request: RunRequest,
    run_storage: "RunStorage",
    broadcaster: EventBroadcaster,
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

        # 5. 更新状态
        run_storage.update_status(
            run_id,
            result.status,
            result=result.output,
            error=result.error,
        )

        await broadcaster.emit_complete(run_id, result.to_dict())

    except Exception as e:
        logger.error(f"Workflow {run_id} failed: {e}", exc_info=True)
        run_storage.update_status(run_id, "failed", error=str(e))
        await broadcaster.emit(run_id, "error", {"message": str(e)})
        await broadcaster.unsubscribe(run_id)
    finally:
        # 清理注册
        unregister_workflow_engine(run_id)


# 允许直接运行: uvicorn api.main:app --reload
try:
    app = create_app()
except ImportError:
    app = None
