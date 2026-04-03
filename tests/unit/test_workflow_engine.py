"""WorkflowEngine 单元测试"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import sys
import tempfile
import shutil

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tutor.core.workflow.base import (
    WorkflowEngine,
    Workflow,
    WorkflowStep,
    WorkflowContext,
    WorkflowStatus,
    WorkflowResult,
    CheckpointData,
)


class TestWorkflowStatus:
    """测试 WorkflowStatus 状态常量"""

    def test_status_values(self):
        """测试状态值"""
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.PAUSED == "paused"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"
        assert WorkflowStatus.CANCELLED == "cancelled"


class TestCheckpointData:
    """测试 CheckpointData 数据类"""

    def test_to_dict(self):
        """测试转换为字典"""
        checkpoint = CheckpointData(
            workflow_id="test-123",
            workflow_type="idea",
            status=WorkflowStatus.RUNNING,
            current_step=2,
            total_steps=5,
            step_name="analyze",
            input_data={"key": "value"},
            output_data={"result": "ok"},
            error=None,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:01:00Z",
        )
        d = checkpoint.to_dict()
        assert d["workflow_id"] == "test-123"
        assert d["status"] == "running"
        assert d["current_step"] == 2

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "workflow_id": "test-456",
            "workflow_type": "experiment",
            "status": "completed",
            "current_step": 3,
            "total_steps": 4,
            "step_name": "run",
            "input_data": {},
            "output_data": {"output": "result"},
            "error": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:02:00Z",
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.workflow_id == "test-456"
        assert checkpoint.workflow_type == "experiment"
        assert checkpoint.status == "completed"

    def test_from_dict_with_extra_fields(self):
        """测试从字典创建时忽略额外字段"""
        data = {
            "workflow_id": "test-789",
            "workflow_type": "idea",
            "status": "running",
            "current_step": 1,
            "total_steps": 2,
            "step_name": "start",
            "input_data": {},
            "output_data": {},
            "error": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "_crc32": 12345,  # 额外字段应该被忽略
            "unknown_field": "should be ignored",
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.workflow_id == "test-789"


class TestWorkflowStep:
    """测试 WorkflowStep 基类"""

    def test_step_creation(self):
        """测试步骤创建"""
        step = WorkflowStep(name="test_step", description="A test step")
        assert step.name == "test_step"
        assert step.description == "A test step"

    def test_execute_not_implemented(self):
        """测试 execute 方法未实现时抛出异常"""
        step = WorkflowStep(name="test", description="test")

        with pytest.raises(NotImplementedError):
            step.execute(Mock())

    def test_validate_returns_empty_list(self):
        """测试 validate 默认返回空列表"""
        step = WorkflowStep(name="test", description="test")
        result = step.validate(Mock())
        assert result == []

    def test_rollback_logs_warning(self):
        """测试 rollback 默认只记录警告"""
        step = WorkflowStep(name="test", description="test")
        # 不应抛出异常，只记录警告
        step.rollback(Mock())


class MockWorkflowStep(WorkflowStep):
    """模拟工作流步骤用于测试"""

    def __init__(self, name: str = "mock_step", should_fail: bool = False):
        super().__init__(name, "A mock step for testing")
        self.should_fail = should_fail
        self.execute_called = False
        self.rollback_called = False

    def execute(self, context: WorkflowContext) -> dict:
        self.execute_called = True
        if self.should_fail:
            raise ValueError("Mock step failure")
        return {"result": f"{self.name}_result"}

    def rollback(self, context: WorkflowContext) -> None:
        self.rollback_called = True


class MockWorkflow(Workflow):
    """模拟工作流用于测试"""

    def __init__(self, workflow_id: str, config: dict, storage_path: Path,
                 model_gateway=None, broadcaster=None):
        super().__init__(
            workflow_id=workflow_id,
            config=config,
            storage_path=storage_path,
            model_gateway=model_gateway or Mock()
        )
        self.build_steps_called = False

    def build_steps(self):
        self.build_steps_called = True
        return [
            MockWorkflowStep("step1"),
            MockWorkflowStep("step2"),
            MockWorkflowStep("step3"),
        ]


class TestWorkflowContext:
    """测试 WorkflowContext 类"""

    def test_initialization(self, tmp_path):
        """测试初始化"""
        context = WorkflowContext(
            workflow_id="test-123",
            config={"type": "idea", "steps": 3},
            storage_path=tmp_path,
            model_gateway=Mock()
        )
        assert context.workflow_id == "test-123"
        assert context.config["type"] == "idea"

    def test_get_set_state(self, tmp_path):
        """测试状态存取"""
        context = WorkflowContext(
            workflow_id="test",
            config={},
            storage_path=tmp_path,
            model_gateway=Mock()
        )
        context.set_state("key1", "value1")
        assert context.get_state("key1") == "value1"
        assert context.get_state("nonexistent", "default") == "default"

    def test_update_state(self, tmp_path):
        """测试批量更新状态"""
        context = WorkflowContext(
            workflow_id="test",
            config={},
            storage_path=tmp_path,
            model_gateway=Mock()
        )
        context.update_state({"a": 1, "b": 2})
        assert context.get_state("a") == 1
        assert context.get_state("b") == 2

    def test_get_checkpoint_path(self, tmp_path):
        """测试检查点路径生成"""
        context = WorkflowContext(
            workflow_id="test",
            config={},
            storage_path=tmp_path,
            model_gateway=Mock()
        )
        path = context.get_checkpoint_path(5)
        assert path.name == "step_0005.json"


class TestWorkflow:
    """测试 Workflow 基类"""

    def test_workflow_initialization(self, tmp_path):
        """测试工作流初始化"""
        workflow = MockWorkflow("test-workflow", {"type": "test"}, tmp_path)
        assert workflow.workflow_id == "test-workflow"
        assert workflow.config["type"] == "test"

    def test_build_steps(self, tmp_path):
        """测试构建步骤"""
        workflow = MockWorkflow("test", {}, tmp_path)
        steps = workflow.build_steps()
        assert len(steps) == 3
        assert all(isinstance(s, WorkflowStep) for s in steps)

    def test_get_progress_empty(self, tmp_path):
        """测试空工作流进度"""
        workflow = MockWorkflow("test", {}, tmp_path)
        progress = workflow.get_progress()
        assert progress["total_steps"] == 0
        assert progress["current_step"] == 0
        assert progress["percent"] == 0.0

    def test_get_progress_with_steps(self, tmp_path):
        """测试有步骤的工作流进度"""
        workflow = MockWorkflow("test", {}, tmp_path)
        workflow.initialize()
        progress = workflow.get_progress()
        assert progress["total_steps"] == 3
        assert progress["current_step"] == 0

    def test_workflow_run_success(self, tmp_path):
        """测试工作流成功运行"""
        workflow = MockWorkflow("test-run", {}, tmp_path)
        result = workflow.run()

        assert result.status == WorkflowStatus.COMPLETED
        assert result.workflow_id == "test-run"
        assert result.error is None

        # 验证所有步骤都被执行
        for step in workflow.steps:
            if isinstance(step, MockWorkflowStep):
                assert step.execute_called is True


class TestWorkflowEngine:
    """测试 WorkflowEngine 类"""

    def test_engine_initialization(self, tmp_path):
        """测试引擎初始化"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)
        assert engine.storage_path == tmp_path
        assert engine.model_gateway == gateway
        assert len(engine.active_workflows) == 0

    def test_create_workflow(self, tmp_path):
        """测试创建工作流"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        workflow = engine.create_workflow(
            MockWorkflow, "new-workflow", {"type": "test"}
        )

        assert workflow.workflow_id == "new-workflow"
        assert "new-workflow" in engine.active_workflows

    def test_create_duplicate_workflow_raises(self, tmp_path):
        """测试创建重复 ID 的工作流抛出异常"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        engine.create_workflow(MockWorkflow, "dup-id", {})

        with pytest.raises(ValueError, match="already exists"):
            engine.create_workflow(MockWorkflow, "dup-id", {})

    def test_get_workflow(self, tmp_path):
        """测试获取工作流"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        created = engine.create_workflow(MockWorkflow, "get-test", {})
        retrieved = engine.get_workflow("get-test")

        assert created is retrieved

    def test_get_nonexistent_workflow(self, tmp_path):
        """测试获取不存在的工作流返回 None"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        result = engine.get_workflow("nonexistent")
        assert result is None

    def test_list_workflows(self, tmp_path):
        """测试列出工作流"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        engine.create_workflow(MockWorkflow, "wf1", {"type": "idea"})
        engine.create_workflow(MockWorkflow, "wf2", {"type": "experiment"})

        workflows = engine.list_workflows()
        assert len(workflows) == 2

    def test_run_workflow(self, tmp_path):
        """测试运行工作流"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        workflow = engine.create_workflow(MockWorkflow, "run-test", {})
        result = engine.run_workflow("run-test")

        assert result.status == WorkflowStatus.COMPLETED

    def test_run_nonexistent_workflow_raises(self, tmp_path):
        """测试运行不存在的工作流抛出异常"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        with pytest.raises(ValueError, match="not found"):
            engine.run_workflow("nonexistent")

    def test_cleanup_workflow(self, tmp_path):
        """测试清理工作流"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        engine.create_workflow(MockWorkflow, "cleanup-test", {})
        assert engine.cleanup_workflow("cleanup-test") is True
        assert "cleanup-test" not in engine.active_workflows

    def test_cleanup_nonexistent_workflow(self, tmp_path):
        """测试清理不存在的工作流"""
        gateway = Mock()
        engine = WorkflowEngine(tmp_path, gateway)

        assert engine.cleanup_workflow("nonexistent") is False


class TestWorkflowResult:
    """测试 WorkflowResult 数据类"""

    def test_to_dict(self):
        """测试转换为字典"""
        from datetime import datetime, timezone

        result = WorkflowResult(
            workflow_id="test-result",
            status=WorkflowStatus.COMPLETED,
            output={"key": "value"},
            error=None,
            started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc),
            duration_seconds=3600.0,
        )

        d = result.to_dict()
        assert d["workflow_id"] == "test-result"
        assert d["status"] == "completed"
        assert d["output"] == {"key": "value"}
        assert d["duration_seconds"] == 3600.0
