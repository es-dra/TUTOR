"""Storage package for TUTOR.

Provides repository interface and implementations for workflow run storage.
"""

# Repository Protocol
from tutor.core.storage.repository import WorkflowRunRepository

# Factory
from tutor.core.storage.factory import get_repository, reset_repository

# Legacy storage (for backward compatibility)
from tutor.core.storage.workflow_runs import RunStorage

__all__ = [
    # Repository interface
    "WorkflowRunRepository",
    # Factory
    "get_repository",
    "reset_repository",
    # Legacy (for compatibility)
    "RunStorage",
]
