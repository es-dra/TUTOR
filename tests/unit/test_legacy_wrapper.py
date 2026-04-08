"""Tests for LegacyWorkflowRunRepository wrapper."""
import pytest


@pytest.mark.unit
def test_legacy_wrapper_implements_protocol():
    """Verify LegacyWorkflowRunRepository implements WorkflowRunRepository."""
    from tutor.core.storage.legacy_impl import LegacyWorkflowRunRepository
    from tutor.core.storage.repository import WorkflowRunRepository

    wrapper = LegacyWorkflowRunRepository()
    assert isinstance(wrapper, WorkflowRunRepository)


@pytest.mark.unit
def test_legacy_wrapper_creates_run():
    """Test creating a run via legacy wrapper."""
    from tutor.core.storage.legacy_impl import LegacyWorkflowRunRepository

    wrapper = LegacyWorkflowRunRepository()
    result = wrapper.create_run("run-1", "idea")

    assert result["run_id"] == "run-1"
    assert result["workflow_type"] == "idea"
    assert result["status"] == "pending"
