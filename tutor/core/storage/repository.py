"""Repository interface for workflow run storage.

This module defines the WorkflowRunRepository Protocol (interface)
that all storage implementations must follow.
"""

from typing import Any, Dict, List, Optional, Protocol


class WorkflowRunRepository(Protocol):
    """Protocol for workflow run storage operations.

    All implementations must provide these methods:
    - create_run: Create a new workflow run
    - get_run: Get a workflow run by ID
    - update_status: Update run status
    - list_runs: List runs with optional filters
    - delete_run: Delete a run
    - update_tags: Update run tags
    - list_runs_by_tags: List runs by tags
    - add_event: Add an event to run history
    - get_events: Get events for a run
    - get_stats: Get run statistics
    """

    def create_run(
        self,
        run_id: str,
        workflow_type: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new workflow run record.

        Args:
            run_id: Unique identifier for the run
            workflow_type: Type of workflow (idea, experiment, review, write)
            params: Workflow parameters
            config: Run configuration

        Returns:
            The created run record as a dictionary
        """
        ...

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a workflow run by ID.

        Args:
            run_id: The run identifier

        Returns:
            The run record or None if not found
        """
        ...

    def update_status(
        self,
        run_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update the status of a workflow run.

        Args:
            run_id: The run identifier
            status: New status (pending, running, completed, failed, cancelled)
            result: Optional result data
            error: Optional error message
            usage: Optional usage statistics

        Returns:
            True if update succeeded, False otherwise
        """
        ...

    def list_runs(
        self,
        status: Optional[str] = None,
        workflow_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List workflow runs with optional filtering.

        Args:
            status: Filter by status
            workflow_type: Filter by workflow type
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            Dict with 'total' and 'runs' keys
        """
        ...

    def delete_run(self, run_id: str) -> bool:
        """Delete a workflow run.

        Args:
            run_id: The run identifier

        Returns:
            True if deleted, False if not found
        """
        ...

    def update_tags(self, run_id: str, tags: List[str]) -> bool:
        """Update tags for a workflow run.

        Args:
            run_id: The run identifier
            tags: List of tags

        Returns:
            True if update succeeded, False otherwise
        """
        ...

    def list_runs_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List workflow runs by tags.

        Args:
            tags: Tags to filter by
            match_all: If True, all tags must match; if False, any tag matches
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of matching run records
        """
        ...

    def add_event(
        self,
        run_id: str,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add an event to a workflow run's history.

        Args:
            run_id: The run identifier
            event_type: Type of event
            event_data: Event data
        """
        ...

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all events for a workflow run.

        Args:
            run_id: The run identifier

        Returns:
            List of event records
        """
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Get workflow run statistics.

        Returns:
            Dict with 'total', 'by_status', and 'by_type' keys
        """
        ...
