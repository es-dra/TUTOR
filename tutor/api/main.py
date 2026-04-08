"""TUTOR Web API 主应用

FastAPI应用，提供：
- RESTful 工作流执行接口
- Server-Sent Events (SSE) 实时进度推送
- 健康检查与OpenAPI文档
"""

import asyncio
import hmac
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse, StreamingResponse
except ImportError:
    HTTPException = Exception
    JSONResponse = None
    StreamingResponse = None
    Fast = None

from tutor.api.models import (
    error_response,
    paginated_response,
    success_response,
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
        if client_id not in self.requests or not self.requests[client_id]:
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

    # Validate API key using timing-safe comparison
    if not api_key:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "detail": "Missing X-API-Key header",
            },
        )
    if not hmac.compare_digest(api_key, expected_key):
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "detail": "Invalid X-API-Key header",
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
    from tutor.core.storage import get_repository

    run_storage = get_repository()

    @app.get("/metrics", tags=["system"])
    async def prometheus_metrics():
        """Prometheus metrics endpoint"""
        from tutor.api.prometheus import get_metrics

        metrics = get_metrics()
        return StreamingResponse(
            iter([metrics.format_prometheus()]), media_type="text/plain"
        )

    # --- API v1 Routes ---
    # Health check endpoints
    from tutor.api.routes.health import router as health_router

    app.include_router(health_router)

    # Legacy compatibility routes (deprecated)
    from tutor.api.routes.legacy import router as legacy_router

    app.include_router(legacy_router)

    # 工作流管理端点
    from tutor.api.routes.workflows import router as workflows_router

    app.include_router(workflows_router)

    # 事件流端点
    from tutor.api.routes.events import router as events_router

    app.include_router(events_router)

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

    # WebSocket 端点 - 角色实时互动
    from tutor.api.routes.websockets import router as websockets_router

    app.include_router(websockets_router)

    # V3 Project 端点 - 新一代项目管理
    from tutor.api.routes.v3_projects import router as v3_projects_router

    app.include_router(v3_projects_router)

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
        import os
        from pathlib import Path

        from tutor.core.model import ModelGateway
        from tutor.core.workflow.base import (
            WorkflowEngine,
            register_workflow_engine,
            unregister_workflow_engine,
        )

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
