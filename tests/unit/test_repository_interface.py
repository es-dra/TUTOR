"""Tests for WorkflowRunRepository interface."""
import pytest
from typing import Protocol


@pytest.mark.unit
def test_repository_protocol_exists():
    """Verify WorkflowRunRepository Protocol is importable."""
    from tutor.core.storage.repository import WorkflowRunRepository
    assert issubclass(WorkflowRunRepository, Protocol)


@pytest.mark.unit
def test_repository_has_required_methods():
    """Verify WorkflowRunRepository has all required methods."""
    from tutor.core.storage.repository import WorkflowRunRepository
    import inspect

    required_methods = [
        'create_run', 'get_run', 'update_status', 'list_runs',
        'delete_run', 'update_tags', 'list_runs_by_tags',
        'add_event', 'get_events', 'get_stats'
    ]

    for method in required_methods:
        assert hasattr(WorkflowRunRepository, method), f"Missing method: {method}"
