"""CLI TUI 单元测试"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tutor.cli.tui import (
    TUIState,
    DashboardRenderer,
    RunDetailRenderer,
    WorkflowRunner,
    InteractiveTUI,
)


# --- TUIState Tests ---

class TestTUIState:
    def test_initial_state(self):
        state = TUIState()
        assert state.current_screen == "dashboard"
        assert state.get_runs() == []

    def test_add_and_get_runs(self):
        state = TUIState()
        state.add_run({"run_id": "r1", "status": "completed", "workflow_type": "idea"})
        state.add_run({"run_id": "r2", "status": "running", "workflow_type": "review"})
        assert len(state.get_runs()) == 2
        assert len(state.get_runs("completed")) == 1
        assert len(state.get_runs("running")) == 1

    def test_get_run_by_id(self):
        state = TUIState()
        state.add_run({"run_id": "abc", "status": "completed"})
        assert state.get_run("abc")["status"] == "completed"
        assert state.get_run("nonexistent") is None

    def test_update_run(self):
        state = TUIState()
        state.add_run({"run_id": "r1", "status": "pending", "result": None})
        state.update_run("r1", status="completed", result={"msg": "done"})
        assert state.get_run("r1")["status"] == "completed"
        assert state.get_run("r1")["result"]["msg"] == "done"


# --- DashboardRenderer Tests ---

class TestDashboardRenderer:
    def test_workflow_info_complete(self):
        info = DashboardRenderer.WORKFLOW_INFO
        assert "idea" in info
        assert "write" in info
        assert "latex" in info
        assert "adversarial_review" in info
        assert len(info) >= 6

    def test_render_without_rich(self, capsys):
        console = MagicMock()
        # Mock Rich not available
        with patch.dict("sys.modules", {"rich.console": None}):
            DashboardRenderer.render(console, TUIState())
            # Should not crash


# --- RunDetailRenderer Tests ---

class TestRunDetailRenderer:
    def test_render_with_result(self, capsys):
        console = MagicMock()
        run_data = {
            "run_id": "abc",
            "workflow_type": "idea",
            "status": "completed",
            "started_at": "2026-03-20T10:00:00Z",
            "completed_at": "2026-03-20T10:05:00Z",
            "result": {"ideas": ["idea1", "idea2"]},
        }
        with patch.dict("sys.modules", {"rich": MagicMock()}):
            RunDetailRenderer.render(console, run_data)

    def test_render_with_error(self, capsys):
        console = MagicMock()
        run_data = {
            "run_id": "abc",
            "status": "failed",
            "error": "Something went wrong",
        }
        with patch.dict("sys.modules", {"rich": MagicMock()}):
            RunDetailRenderer.render(console, run_data)


# --- WorkflowRunner Tests ---

class TestWorkflowRunner:
    def test_run_success(self):
        console = MagicMock()
        state = TUIState()
        runner = WorkflowRunner(console, state)

        result = runner.run_workflow("idea", {"topic": "test"})
        assert result is not None
        assert len(state.get_runs()) == 1
        assert state.get_runs()[0]["status"] == "completed"

    def test_run_failure(self):
        console = MagicMock()
        state = TUIState()
        runner = WorkflowRunner(console, state)

        with patch.object(runner, "_execute", side_effect=RuntimeError("test error")):
            result = runner.run_workflow("idea", {"topic": "test"})
            assert state.get_runs()[0]["status"] == "failed"
            assert "test error" in state.get_runs()[0]["error"]


# --- InteractiveTUI Tests ---

class TestInteractiveTUI:
    def test_initialization(self):
        tui = InteractiveTUI()
        assert tui.state.current_screen == "dashboard"
