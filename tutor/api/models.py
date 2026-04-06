"""Pydantic models for API requests/responses and SSE events."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tutor.core.workflow.base import WorkflowStatus as WorkflowStatusEnum

# Re-export for backward compatibility
WorkflowStatus = WorkflowStatusEnum


class RunWorkflowRequest(BaseModel):
    """Request to start a workflow run."""

    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    config_override: Optional[Dict[str, Any]] = Field(default_factory=dict)


class WorkflowRunSummary(BaseModel):
    """Summary of a workflow run."""

    run_id: str
    workflow_name: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    current_step: Optional[str] = None
    error: Optional[str] = None


class StepEvent(BaseModel):
    """Event emitted when a step completes."""

    run_id: str
    step_name: str
    status: WorkflowStatus
    message: Optional[str] = None


class LogEvent(BaseModel):
    """Event for log messages."""

    run_id: str
    level: str = Field(..., description="Log level: info, warning, error")
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowFinishedEvent(BaseModel):
    """Event emitted when workflow finishes."""

    run_id: str
    status: WorkflowStatus
    final_output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# Union type for all SSE events
class SSEMessage(BaseModel):
    """Wrapper for all SSE messages."""

    event: str  # "workflow_started", "step_completed", "log", "workflow_finished"
    data: Dict[str, Any]
    run_id: str


# ============================================================
# Unified API Response Envelope
# ============================================================


class ApiResponse(BaseModel):
    """统一 API 响应封装

    所有成功响应都使用此格式:
    {
        "success": true,
        "data": { ... },
        "meta": { ... }  // 可选，元数据如分页信息
    }

    错误响应:
    {
        "success": false,
        "error": {
            "code": "ERROR_CODE",
            "message": "错误描述"
        }
    }
    """

    success: bool = True
    data: Optional[Any] = None
    meta: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None


class PaginatedResponse(BaseModel):
    """分页响应格式"""

    success: bool = True
    data: list = Field(default_factory=list)
    meta: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total": 0,
            "limit": 100,
            "offset": 0,
            "has_more": False,
        }
    )
    error: Optional[Dict[str, str]] = None


def success_response(data: Any = None, meta: Dict[str, Any] = None) -> Dict[str, Any]:
    """构造成功响应"""
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if meta is not None:
        response["meta"] = meta
    return response


def error_response(code: str, message: str) -> Dict[str, Any]:
    """构造错误响应"""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


def paginated_response(
    items: list,
    total: int,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """构造分页响应"""
    return {
        "success": True,
        "data": items,
        "meta": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        },
    }
