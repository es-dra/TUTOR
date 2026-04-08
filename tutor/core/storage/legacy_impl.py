"""Legacy SQLite implementation wrapper.

This module wraps the existing RunStorage class to implement
the WorkflowRunRepository Protocol, allowing for backward compatibility
during migration.
"""

import logging
from typing import Any, Dict, List, Optional

from tutor.core.storage.repository import WorkflowRunRepository
from tutor.core.storage.workflow_runs import RunStorage

logger = logging.getLogger(__name__)


class LegacyWorkflowRunRepository(WorkflowRunRepository):
    """Wrapper around original RunStorage to implement WorkflowRunRepository.

    This allows existing code to use the new repository interface
    without requiring immediate migration to SQLAlchemy.
    """

    def __init__(self, db_path: str = "data/tutor_runs.db"):
        """Initialize with legacy RunStorage.

        Args:
            db_path: Path to SQLite database file
        """
        self._storage = RunStorage(db_path=db_path)

    def create_run(
        self,
        run_id: str,
        workflow_type: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new workflow run record."""
        return self._storage.create_run(run_id, workflow_type, params, config)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a workflow run by ID."""
        return self._storage.get_run(run_id)

    def update_status(
        self,
        run_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update the status of a workflow run."""
        return self._storage.update_status(run_id, status, result, error, usage)

    def list_runs(
        self,
        status: Optional[str] = None,
        workflow_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List workflow runs with optional filtering."""
        return self._storage.list_runs(status, workflow_type, limit, offset)

    def delete_run(self, run_id: str) -> bool:
        """Delete a workflow run."""
        return self._storage.delete_run(run_id)

    def update_tags(self, run_id: str, tags: List[str]) -> bool:
        """Update tags for a workflow run."""
        return self._storage.update_tags(run_id, tags)

    def list_runs_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List workflow runs by tags."""
        return self._storage.list_runs_by_tags(tags, match_all, limit, offset)

    def add_event(
        self,
        run_id: str,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add an event to a workflow run's history."""
        self._storage.add_event(run_id, event_type, event_data)

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all events for a workflow run."""
        return self._storage.get_events(run_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get workflow run statistics."""
        return self._storage.get_stats()
