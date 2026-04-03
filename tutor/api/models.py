"""Pydantic models for API requests/responses and SSE events."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class WorkflowName(str, Enum):
    IDEA = "idea"
    EXPERIMENT = "experiment"
    REVIEW = "review"
    WRITE = "write"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


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
