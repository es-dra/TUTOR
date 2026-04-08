"""Tests for Repository Factory."""
import pytest
import os


@pytest.mark.unit
def test_factory_returns_repository():
    """Verify factory returns a repository instance."""
    from tutor.core.storage.factory import get_repository
    from tutor.core.storage.repository import WorkflowRunRepository

    repo = get_repository()
    assert isinstance(repo, WorkflowRunRepository)


@pytest.mark.unit
def test_factory_returns_same_instance():
    """Verify factory returns the same instance on repeated calls."""
    from tutor.core.storage.factory import get_repository, reset_repository

    reset_repository()
    repo1 = get_repository()
    repo2 = get_repository()

    assert repo1 is repo2


@pytest.mark.unit
def test_reset_repository():
    """Verify reset_repository clears the cached instance."""
    from tutor.core.storage.factory import get_repository, reset_repository

    repo1 = get_repository()
    reset_repository()
    repo2 = get_repository()

    assert repo1 is not repo2
