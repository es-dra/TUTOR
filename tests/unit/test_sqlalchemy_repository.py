"""Tests for SQLAlchemyWorkflowRunRepository."""
import pytest


@pytest.mark.unit
def test_sqlalchemy_repository_implements_protocol():
    """Verify SQLAlchemyRepository implements WorkflowRunRepository."""
    from tutor.core.storage.sqlalchemy_impl import SQLAlchemyWorkflowRunRepository
    from tutor.core.storage.repository import WorkflowRunRepository

    # Create in-memory database
    repo = SQLAlchemyWorkflowRunRepository(db_url="sqlite:///:memory:")

    # Check it's an instance of the protocol
    assert isinstance(repo, WorkflowRunRepository)


@pytest.mark.unit
def test_create_run():
    """Test creating a workflow run."""
    from tutor.core.storage.sqlalchemy_impl import SQLAlchemyWorkflowRunRepository

    repo = SQLAlchemyWorkflowRunRepository(db_url="sqlite:///:memory:")
    result = repo.create_run("run-1", "idea", params={"test": "value"})

    assert result["run_id"] == "run-1"
    assert result["workflow_type"] == "idea"
    assert result["status"] == "pending"
    assert result["params"] == {"test": "value"}


@pytest.mark.unit
def test_get_run():
    """Test getting a workflow run."""
    from tutor.core.storage.sqlalchemy_impl import SQLAlchemyWorkflowRunRepository

    repo = SQLAlchemyWorkflowRunRepository(db_url="sqlite:///:memory:")
    repo.create_run("run-1", "idea")
    result = repo.get_run("run-1")

    assert result is not None
    assert result["run_id"] == "run-1"


@pytest.mark.unit
def test_update_status():
    """Test updating workflow run status."""
    from tutor.core.storage.sqlalchemy_impl import SQLAlchemyWorkflowRunRepository

    repo = SQLAlchemyWorkflowRunRepository(db_url="sqlite:///:memory:")
    repo.create_run("run-1", "idea")
    success = repo.update_status("run-1", "running")

    assert success is True
    run = repo.get_run("run-1")
    assert run["status"] == "running"


@pytest.mark.unit
def test_update_status_completed():
    """Test updating status to completed with result."""
    from tutor.core.storage.sqlalchemy_impl import SQLAlchemyWorkflowRunRepository

    repo = SQLAlchemyWorkflowRunRepository(db_url="sqlite:///:memory:")
    repo.create_run("run-1", "idea")
    repo.update_status("run-1", "running")
    repo.update_status(
        "run-1",
        "completed",
        result={"output": "test result"},
        usage={"tokens": 100},
    )

    run = repo.get_run("run-1")
    assert run["status"] == "completed"
    assert run["result"] == {"output": "test result"}
    assert run["usage"] == {"tokens": 100}
