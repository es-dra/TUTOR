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
        "/api/v1/providers",
    }

    # Public paths that start with these prefixes (no auth required)
    public_prefixes = [
        "/api/v1/providers/",
    ]

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
        self._subscribers: Dict[str, asyncio.Queue] = {}

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        """订阅指定run的事件流"""
        queue = asyncio.Queue(maxsize=100)
        self._subscribers[run_id] = queue
        logger.debug(f"SSE subscriber added for run {run_id}")
        return queue

    async def unsubscribe(self, run_id: str) -> None:
        """取消订阅"""
        self._subscribers.pop(run_id, None)
        logger.debug(f"SSE subscriber removed for run {run_id}")

    async def emit(self, run_id: str, event_type: str, data: Any) -> None:
        """发送事件到所有订阅者"""
        queue = self._subscribers.get(run_id)
        if queue:
            event = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            }
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Event queue full for run {run_id}, dropping event")

    async def emit_complete(self, run_id: str, result: Any) -> None:
        """发送完成事件并关闭队列"""
        await self.emit(run_id, "complete", result)
        await self.unsubscribe(run_id)


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
    workflow_type: str = Field(..., description="工作流类型: idea/experiment/review/write")
    params: Dict[str, Any] = Field(default_factory=dict, description="工作流参数")
    config: Optional[Dict[str, Any]] = Field(default=None, description="运行配置覆盖")


class RunResponse(BaseModel):
    """工作流执行响应"""
    run_id: str
    status: str
    workflow_type: str
    message: str


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
        logger.error(
            "FastAPI not installed. Install with: pip install fastapi uvicorn"
        )
        raise

    app = FastAPI(
        title="TUTOR API",
        description="TUTOR智能研究自动化平台 Web API",
        version="0.2.0",
    )

    # 添加中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
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
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat() + "Z"}

    @app.get("/health/live", tags=["system"])
    async def health_live():
        """Liveness Probe - 应用是否存活"""
        return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat() + "Z"}

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
        return StreamingResponse(iter([metrics.format_prometheus()]), media_type="text/plain")

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

        run_id = str(uuid.uuid4())[:8]
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

    @app.get("/runs/{run_id}", response_model=RunStatusResponse, tags=["workflow"])
    async def get_run_status(run_id: str):
        """查询运行状态"""
        run = run_storage.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return RunStatusResponse(**run)

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
        return result

    @app.get("/stats", tags=["workflow"])
    async def get_stats():
        """获取工作流运行统计"""
        return run_storage.get_stats()

    # 注意：这些特定路径必须在 /runs/{run_id} 之前定义，否则会被当作 run_id
    @app.get("/runs/list/archived", tags=["workflow"])
    async def list_archived_runs(limit: int = 100, offset: int = 0):
        """列出已归档的工作流"""
        runs = run_storage.list_runs_by_tags(["archived"], match_all=False, limit=limit, offset=offset)
        return {"total": len(runs), "runs": runs}

    @app.get("/runs/list/favorites", tags=["workflow"])
    async def list_favorite_runs(limit: int = 100, offset: int = 0):
        """列出收藏的工作流"""
        runs = run_storage.list_runs_by_tags(["favorite"], match_all=False, limit=limit, offset=offset)
        return {"total": len(runs), "runs": runs}

    @app.delete("/runs/{run_id}", tags=["workflow"])
    async def delete_run(run_id: str):
        """删除工作流运行记录"""
        success = run_storage.delete_run(run_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return {"status": "deleted", "run_id": run_id}

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
        return updated_run

    @app.post("/runs/{run_id}/cancel", tags=["workflow"])
    async def cancel_run(run_id: str):
        """取消运行中的工作流"""
        run = run_storage.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        if run["status"] not in ["pending", "running"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel run in status '{run['status']}'"
            )

        run_storage.update_status(run_id, "cancelled")

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
                await broadcaster.unsubscribe(run_id)

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
            raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
        return request.to_dict()

    @app.post("/approvals/{approval_id}/approve", tags=["approvals"])
    async def approve_request(approval_id: str, comment: Optional[str] = ""):
        """Approve an approval request"""
        success = am.approve(approval_id, comment=comment or "")
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve '{approval_id}'. Not found or already resolved.",
            )
        request = am.get_request(approval_id)
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
            raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
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
        result = await asyncio.to_thread(engine.run_workflow, run_id)

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
