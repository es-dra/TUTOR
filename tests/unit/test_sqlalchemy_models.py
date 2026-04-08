"""Tests for SQLAlchemy ORM models."""
import pytest


@pytest.mark.unit
def test_workflow_run_model_exists():
    """Verify WorkflowRun model exists."""
    from tutor.core.storage.models import WorkflowRun
    assert WorkflowRun is not None


@pytest.mark.unit
def test_run_event_model_exists():
    """Verify RunEvent model exists."""
    from tutor.core.storage.models import RunEvent
    assert RunEvent is not None


@pytest.mark.unit
def test_models_have_required_columns():
    """Verify models have required columns."""
    from tutor.core.storage.models import WorkflowRun, RunEvent
    from sqlalchemy import inspect

    run_columns = [c.key for c in inspect(WorkflowRun).columns]
    assert 'run_id' in run_columns
    assert 'workflow_type' in run_columns
    assert 'status' in run_columns
    assert 'params' in run_columns
    assert 'config' in run_columns

    event_columns = [c.key for c in inspect(RunEvent).columns]
    assert 'id' in event_columns
    assert 'run_id' in event_columns
    assert 'event_type' in event_columns
    assert 'event_data' in event_columns
