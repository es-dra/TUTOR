"""ApprovalStep + ApprovalManager 单元测试"""

import asyncio
import time
from datetime import datetime, timezone

import pytest

from tutor.core.workflow.approval import (
    ApprovalStep,
    ApprovalManager,
    ApprovalStatus,
    ApprovalRequest,
)


# --- Fixtures ---

@pytest.fixture
def manager():
    return ApprovalManager()


@pytest.fixture
def sample_request(manager):
    return manager.create_request(
        approval_id="test-approval-1",
        run_id="run-001",
        title="Review experiment results",
        description="Please review before proceeding",
        context_data={"metric": 0.95},
        timeout_seconds=10,
    )


# --- ApprovalRequest Tests ---

class TestApprovalRequest:
    def test_initial_state(self, sample_request):
        assert sample_request.status == ApprovalStatus.PENDING
        assert sample_request.approval_id == "test-approval-1"
        assert sample_request.run_id == "run-001"

    def test_approve(self, sample_request):
        sample_request.approve(by="admin", comment="LGTM")
        assert sample_request.status == ApprovalStatus.APPROVED
        assert sample_request.resolved_by == "admin"
        assert sample_request.comment == "LGTM"
        assert sample_request.resolved_at is not None

    def test_reject(self, sample_request):
        sample_request.reject(by="reviewer", comment="Needs more data")
        assert sample_request.status == ApprovalStatus.REJECTED
        assert sample_request.comment == "Needs more data"

    def test_cancel(self, sample_request):
        sample_request.cancel()
        assert sample_request.status == ApprovalStatus.CANCELLED

    def test_double_approve_noop(self, sample_request):
        sample_request.approve()
        sample_request.approve()  # Second should be a no-op
        assert sample_request.status == ApprovalStatus.APPROVED
        # resolved_by stays as first approver
        assert sample_request.resolved_by == "user"

    @pytest.mark.asyncio
    async def test_wait_immediate_approval(self, sample_request):
        # Approve before waiting
        sample_request.approve()
        status = await sample_request.wait(timeout=1)
        assert status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_wait_timeout(self, sample_request):
        status = await sample_request.wait(timeout=1)
        assert status == ApprovalStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_wait_then_approve(self, sample_request):
        async def delayed_approve():
            await asyncio.sleep(0.1)
            sample_request.approve()

        task = asyncio.create_task(delayed_approve())
        status = await sample_request.wait(timeout=5)
        await task
        assert status == ApprovalStatus.APPROVED

    def test_to_dict(self, sample_request):
        sample_request.approve(by="admin", comment="OK")
        d = sample_request.to_dict()
        assert d["approval_id"] == "test-approval-1"
        assert d["status"] == "approved"
        assert d["resolved_by"] == "admin"
        assert "created_at" in d
        assert "resolved_at" in d


# --- ApprovalManager Tests ---

class TestApprovalManager:
    def test_create_and_get(self, manager):
        req = manager.create_request("a1", "run-1", "Title")
        assert manager.get_request("a1") is req

    def test_get_nonexistent(self, manager):
        assert manager.get_request("nonexistent") is None

    def test_approve(self, manager):
        manager.create_request("a1", "run-1", "Title")
        result = manager.approve("a1", by="admin", comment="Yes")
        assert result is True
        assert manager.get_request("a1").status == ApprovalStatus.APPROVED

    def test_approve_nonexistent(self, manager):
        assert manager.approve("nonexistent") is False

    def test_approve_already_resolved(self, manager):
        manager.create_request("a1", "run-1", "Title")
        manager.approve("a1")
        assert manager.approve("a1") is False  # Already approved

    def test_reject(self, manager):
        manager.create_request("a1", "run-1", "Title")
        result = manager.reject("a1", comment="No")
        assert result is True
        assert manager.get_request("a1").status == ApprovalStatus.REJECTED

    def test_cancel(self, manager):
        manager.create_request("a1", "run-1", "Title")
        assert manager.cancel("a1") is True
        assert manager.get_request("a1").status == ApprovalStatus.CANCELLED

    def test_list_pending(self, manager):
        manager.create_request("a1", "run-1", "A")
        manager.create_request("a2", "run-1", "B")
        manager.create_request("a3", "run-2", "C")
        manager.approve("a1")

        pending = manager.list_pending()
        assert len(pending) == 2

        pending_run1 = manager.list_pending(run_id="run-1")
        assert len(pending_run1) == 1
        assert pending_run1[0].approval_id == "a2"

    def test_list_all_with_status(self, manager):
        manager.create_request("a1", "run-1", "A")
        manager.create_request("a2", "run-1", "B")
        manager.approve("a1")

        approved = manager.list_all(status="approved")
        assert len(approved) == 1

        pending = manager.list_all(status="pending")
        assert len(pending) == 1

    def test_cleanup(self, manager):
        req = manager.create_request("a1", "run-1", "A", timeout_seconds=1)
        # Simulate resolved long ago
        req.approve()
        req.resolved_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

        removed = manager.cleanup(older_than_seconds=86400)
        assert removed == 1
        assert manager.get_request("a1") is None

    def test_cleanup_keeps_recent(self, manager):
        req = manager.create_request("a1", "run-1", "A")
        req.approve()

        removed = manager.cleanup(older_than_seconds=86400)
        assert removed == 0
        assert manager.get_request("a1") is not None


# --- ApprovalStep Tests ---

class TestApprovalStep:
    def test_step_properties(self):
        step = ApprovalStep(title="Gate 1", description="Review")
        assert step.name == "approval_gate"
        assert "Gate 1" in step.description

    def test_validate_always_valid(self):
        step = ApprovalStep()
        errors = step.validate(None)
        assert errors == []

    def test_execute_approved(self):
        step = ApprovalStep(title="Test Gate", timeout_seconds=2)
        from unittest.mock import MagicMock, patch

        mock_context = MagicMock()
        mock_context.workflow_id = "test-run"

        with patch("tutor.core.workflow.approval.approval_manager") as mock_mgr:
            mock_request = ApprovalRequest(
                approval_id="test-run_approval_gate",
                run_id="test-run",
                title="Test Gate",
            )
            mock_request.approve(by="user", comment="OK")
            mock_mgr.get_request.return_value = mock_request

            result = step.execute(mock_context)

        assert result["approved"] is True
        assert result["comment"] == "OK"

    def test_execute_rejected(self):
        step = ApprovalStep(title="Test Gate", timeout_seconds=2)
        from unittest.mock import MagicMock, patch

        mock_context = MagicMock()
        mock_context.workflow_id = "test-run"

        with patch("tutor.core.workflow.approval.approval_manager") as mock_mgr:
            mock_request = ApprovalRequest(
                approval_id="test-run_approval_gate",
                run_id="test-run",
                title="Test Gate",
            )
            mock_request.reject(by="user", comment="Not ready")
            mock_mgr.get_request.return_value = mock_request

            result = step.execute(mock_context)

        assert result["approved"] is False
        assert "Not ready" in result["reason"]

    def test_execute_creates_new_request(self):
        step = ApprovalStep(title="New Gate", timeout_seconds=2)
        from unittest.mock import MagicMock, patch

        mock_context = MagicMock()
        mock_context.workflow_id = "new-run"

        with patch("tutor.core.workflow.approval.approval_manager") as mock_mgr:
            mock_mgr.get_request.return_value = None
            mock_request = ApprovalRequest(
                approval_id="new-run_approval_gate",
                run_id="new-run",
                title="New Gate",
            )
            mock_request.approve()
            mock_mgr.create_request.return_value = mock_request

            result = step.execute(mock_context)

        assert mock_mgr.create_request.called
        assert result["approved"] is True


# --- ApprovalStatus Tests ---

class TestApprovalStatus:
    def test_values(self):
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.TIMEOUT.value == "timeout"
        assert ApprovalStatus.CANCELLED.value == "cancelled"
