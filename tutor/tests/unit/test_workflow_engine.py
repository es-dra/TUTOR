"""Workflow Engine 单元测试

测试覆盖率目标：
- CheckpointData 序列化/反序列化
- WorkflowContext 状态管理
- WorkflowEngine 工作流生命周期
- 工作流暂停/恢复机制
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import MagicMock, patch
import pytest

from tutor.core.workflow import (
    WorkflowStatus,
    CheckpointData,
    WorkflowResult,
    WorkflowContext,
    WorkflowStep,
    Workflow,
    WorkflowEngine,
)


class TestCheckpointData:
    """CheckpointData 测试"""
    
    def test_create_checkpoint(self):
        """测试：创建检查点"""
        checkpoint = CheckpointData(
            workflow_id="test_wf",
            workflow_type="idea",
            status=WorkflowStatus.RUNNING,
            current_step=1,
            total_steps=5,
            step_name="load_papers",
            input_data={"papers": []},
            output_data={"papers": ["paper1"]},
            error=None,
            created_at="2025-01-15T10:00:00Z",
            updated_at="2025-01-15T10:05:00Z"
        )
        
        assert checkpoint.workflow_id == "test_wf"
        assert checkpoint.status == WorkflowStatus.RUNNING
        assert checkpoint.current_step == 1
        assert checkpoint.output_data["papers"] == ["paper1"]
    
    def test_checkpoint_to_dict(self):
        """测试：转换为字典"""
        checkpoint = CheckpointData(
            workflow_id="test",
            workflow_type="test",
            status=WorkflowStatus.COMPLETED,
            current_step=0,
            total_steps=3,
            step_name="init",
            input_data={},
            output_data={"result": "ok"},
            error=None,
            created_at="2025-01-15T10:00:00Z",
            updated_at="2025-01-15T10:00:00Z"
        )
        
        data = checkpoint.to_dict()
        assert data["workflow_id"] == "test"
        assert data["status"] == WorkflowStatus.COMPLETED
        assert data["output_data"]["result"] == "ok"
    
    def test_checkpoint_from_dict(self):
        """测试：从字典创建"""
        data = {
            "workflow_id": "test",
            "workflow_type": "test",
            "status": WorkflowStatus.RUNNING,
            "current_step": 2,
            "total_steps": 5,
            "step_name": "process",
            "input_data": {"key": "value"},
            "output_data": {"result": "done"},
            "error": None,
            "created_at": "2025-01-15T10:00:00Z",
            "updated_at": "2025-01-15T10:02:00Z"
        }
        
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.workflow_id == "test"
        assert checkpoint.current_step == 2
        assert checkpoint.step_name == "process"
    
    def test_checkpoint_save_and_load(self, tmp_path):
        """测试：保存和加载检查点"""
        checkpoint = CheckpointData(
            workflow_id="test_save",
            workflow_type="test",
            status=WorkflowStatus.RUNNING,
            current_step=1,
            total_steps=3,
            step_name="step1",
            input_data={"input": "test"},
            output_data={"output": "result"},
            error=None,
            created_at="2025-01-15T10:00:00Z",
            updated_at="2025-01-15T10:01:00Z"
        )
        
        # 保存
        save_path = tmp_path / "checkpoints" / "step_0001.json"
        checkpoint.save(save_path)
        
        assert save_path.exists()
        
        # 加载
        loaded = CheckpointData.load(save_path)
        assert loaded.workflow_id == checkpoint.workflow_id
        assert loaded.output_data == checkpoint.output_data
    
    def test_checkpoint_with_error(self):
        """测试：包含错误的检查点"""
        checkpoint = CheckpointData(
            workflow_id="error_test",
            workflow_type="test",
            status=WorkflowStatus.FAILED,
            current_step=2,
            total_steps=4,
            step_name="failing_step",
            input_data={"data": "test"},
            output_data={},
            error="Test error message",
            created_at="2025-01-15T10:00:00Z",
            updated_at="2025-01-15T10:01:00Z"
        )
        
        assert checkpoint.status == WorkflowStatus.FAILED
        assert checkpoint.error == "Test error message"


class TestWorkflowContext:
    """WorkflowContext 测试"""
    
    def test_context_initialization(self, tmp_path):
        """测试：上下文初始化"""
        storage = tmp_path / "storage"
        model_gateway = MagicMock()
        
        context = WorkflowContext(
            workflow_id="test_context",
            config={"type": "idea", "steps": 5},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        assert context.workflow_id == "test_context"
        assert context.config["type"] == "idea"
        assert context.checkpoints_dir == storage / "checkpoints"
        assert context.results_dir == storage / "results"
    
    def test_state_management(self, tmp_path):
        """测试：状态管理"""
        storage = tmp_path / "storage"
        context = WorkflowContext(
            workflow_id="state_test",
            config={},
            storage_path=storage,
            model_gateway=MagicMock()
        )
        
        # 设置和获取状态
        context.set_state("papers", ["paper1", "paper2"])
        context.set_state("current_model", "gpt-4")
        
        assert context.get_state("papers") == ["paper1", "paper2"]
        assert context.get_state("current_model") == "gpt-4"
        assert context.get_state("nonexistent", "default") == "default"
        
        # 批量获取
        all_state = context.get_all_state()
        assert all_state["papers"] == ["paper1", "paper2"]
    
    def test_update_state(self, tmp_path):
        """测试：批量更新状态"""
        storage = tmp_path / "storage"
        context = WorkflowContext(
            workflow_id="update_test",
            config={},
            storage_path=storage,
            model_gateway=MagicMock()
        )
        
        context.set_state("a", 1)
        context.update_state({"b": 2, "c": 3})
        
        all_state = context.get_all_state()
        assert all_state == {"a": 1, "b": 2, "c": 3}
    
    def test_save_and_get_checkpoint(self, tmp_path):
        """测试：保存和获取检查点"""
        storage = tmp_path / "storage"
        model_gateway = MagicMock()
        
        context = WorkflowContext(
            workflow_id="checkpoint_test",
            config={"type": "test", "steps": 3},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        # 保存检查点
        checkpoint = context.save_checkpoint(
            step=1,
            step_name="step_one",
            input_data={"input": "value"},
            output_data={"output": "result"}
        )
        
        assert checkpoint.workflow_id == "checkpoint_test"
        assert checkpoint.current_step == 1
        assert checkpoint.step_name == "step_one"
        
        # 获取最新的检查点
        latest = context.get_latest_checkpoint()
        assert latest is not None
        assert latest.workflow_id == "checkpoint_test"
        assert latest.output_data["output"] == "result"
    
    def test_get_latest_checkpoint_empty(self, tmp_path):
        """测试：无检查点时返回None"""
        storage = tmp_path / "storage"
        context = WorkflowContext(
            workflow_id="no_checkpoint",
            config={},
            storage_path=storage,
            model_gateway=MagicMock()
        )
        
        assert context.get_latest_checkpoint() is None
    
    def test_checkpoint_path_generation(self, tmp_path):
        """测试：检查点路径生成"""
        storage = tmp_path / "storage"
        context = WorkflowContext(
            workflow_id="path_test",
            config={},
            storage_path=storage,
            model_gateway=MagicMock()
        )
        
        path1 = context.get_checkpoint_path(1)
        path5 = context.get_checkpoint_path(5)
        
        assert path1.name == "step_0001.json"
        assert path5.name == "step_0005.json"
        assert path1.parent == path5.parent


class TestWorkflowStep:
    """WorkflowStep 测试"""
    
    def test_step_creation(self):
        """测试：创建步骤"""
        step = WorkflowStep("test_step", "Test step description")
        assert step.name == "test_step"
        assert step.description == "Test step description"
    
    def test_step_str(self):
        """测试：步骤字符串表示"""
        step = WorkflowStep("my_step")
        assert str(step) == "WorkflowStep(my_step)"
    
    def test_step_validate(self):
        """测试：步骤验证（默认通过）"""
        step = WorkflowStep("test")
        context = MagicMock()
        errors = step.validate(context)
        assert errors == []
    
    def test_step_rollback(self, caplog):
        """测试：步骤回滚（默认警告）"""
        step = WorkflowStep("test")
        context = MagicMock()
        step.rollback(context)
        # 应该记录警告
        assert any("Rollback not implemented" in record.message for record in caplog.records)


class TestWorkflow:
    """Workflow 测试"""
    
    def test_workflow_creation(self, tmp_path):
        """测试：创建工作流"""
        storage = tmp_path / "workflows"
        model_gateway = MagicMock()
        
        class TestWorkflow(Workflow):
            def build_steps(self) -> List[WorkflowStep]:
                return [WorkflowStep("step1"), WorkflowStep("step2")]
        
        workflow = TestWorkflow(
            workflow_id="test_workflow",
            config={"type": "test", "steps": 2},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        assert workflow.workflow_id == "test_workflow"
        assert workflow.config["type"] == "test"
        assert len(workflow.steps) == 0  # steps未初始化
    
    def test_workflow_initialize(self, tmp_path):
        """测试：工作流初始化"""
        storage = tmp_path / "workflows"
        model_gateway = MagicMock()
        
        class TestWorkflow(Workflow):
            def build_steps(self) -> List[WorkflowStep]:
                return [
                    WorkflowStep("step1", "First step"),
                    WorkflowStep("step2", "Second step"),
                    WorkflowStep("step3", "Third step")
                ]
        
        workflow = TestWorkflow(
            workflow_id="init_test",
            config={"type": "test"},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        workflow.initialize()
        
        assert len(workflow.steps) == 3
        assert workflow._current_step_index == 0
        
        # 检查是否有历史检查点
        progress = workflow.get_progress()
        assert progress["total_steps"] == 3
        assert progress["current_step"] == 0
    
    def test_workflow_run_success(self, tmp_path):
        """测试：工作流成功执行"""
        storage = tmp_path / "workflows"
        model_gateway = MagicMock()
        
        class SuccessStep(WorkflowStep):
            def execute(self, context):
                context.set_state("step_executed", self.name)
                return {"executed": self.name}
        
        class TestWorkflow(Workflow):
            def build_steps(self) -> List[WorkflowStep]:
                return [
                    SuccessStep("step1"),
                    SuccessStep("step2"),
                ]
        
        workflow = TestWorkflow(
            workflow_id="success_test",
            config={},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        result = workflow.run()
        
        assert result.status == WorkflowStatus.COMPLETED
        assert result.error is None
        assert result.duration_seconds > 0
        assert result.output.get("step_executed") == "step2"
        
        # 检查最终状态
        progress = workflow.get_progress()
        assert progress["current_step"] == 2
        assert progress["total_steps"] == 2
    
    def test_workflow_run_failure(self, tmp_path):
        """测试：工作流执行失败"""
        storage = tmp_path / "workflows"
        model_gateway = MagicMock()
        
        class FailingStep(WorkflowStep):
            def execute(self, context):
                raise ValueError("Step failed!")
        
        class NormalStep(WorkflowStep):
            def execute(self, context):
                return {"step": "done"}
        
        class TestWorkflow(Workflow):
            def build_steps(self) -> List[WorkflowStep]:
                return [NormalStep("normal_step"), FailingStep("failing_step")]
        
        workflow = TestWorkflow(
            workflow_id="failure_test",
            config={},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        result = workflow.run()
        
        assert result.status == WorkflowStatus.FAILED
        assert "Step failed!" in result.error
        assert result.duration_seconds > 0
        
        progress = workflow.get_progress()
        assert progress["current_step"] == 1  # 失败在第2步（索引1）
    
    def test_workflow_validation_error(self, tmp_path):
        """测试：步骤验证失败"""
        storage = tmp_path / "workflows"
        model_gateway = MagicMock()
        
        class ValidatingStep(WorkflowStep):
            def validate(self, context):
                return ["Condition not met"]
        
        class TestWorkflow(Workflow):
            def build_steps(self) -> List[WorkflowStep]:
                return [ValidatingStep("validating_step")]
        
        workflow = TestWorkflow(
            workflow_id="validation_test",
            config={},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        result = workflow.run()
        
        assert result.status == WorkflowStatus.FAILED
        assert "Condition not met" in result.error
    
    def test_workflow_resume_from_checkpoint(self, tmp_path):
        """测试：从检查点恢复"""
        storage = tmp_path / "workflows"
        model_gateway = MagicMock()
        
        class TestStep(WorkflowStep):
            def execute(self, context):
                count = context.get_state("execution_count", 0)
                context.set_state("execution_count", count + 1)
                return {"count": count + 1}
        
        class TestWorkflow(Workflow):
            def build_steps(self) -> List[WorkflowStep]:
                return [TestStep("step1"), TestStep("step2"), TestStep("step3")]
        
        workflow = TestWorkflow(
            workflow_id="resume_test",
            config={"steps": 3},
            storage_path=storage,
            model_gateway=model_gateway
        )
        
        # 第一次运行，执行前两步
        workflow.initialize()
        workflow._current_step_index = 0
        # 手动执行第一步
        step1 = workflow.steps[0]
        step1_output = step1.execute(workflow.context)
        workflow.context.update_state(step1_output)
        workflow.context.save_checkpoint(
            step=0, step_name=step1.name,
            input_data={}, output_data=step1_output
        )
        workflow._current_step_index = 1
        
        # 保存状态后，模拟工作流结束
        result1_path = workflow.context.results_dir / f"{workflow.workflow_id}.json"
        result1_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result1_path, 'w') as f:
            json.dump(workflow.context.get_all_state(), f)
        
        # 创建新的工作流实例（模拟重启）
        workflow2 = TestWorkflow(
            workflow_id="resume_test",
            config={"steps": 3},
            storage_path=storage,
            model_gateway=model_gateway
        )
        workflow2.initialize()
        
        # 应该从step 1恢复
        assert workflow2._current_step_index == 1  # 从检查点恢复
        assert workflow2.context.get_state("count") == 1
    
    def test_workflow_get_result_before_run(self, tmp_path):
        """测试：运行前获取结果"""
        storage = tmp_path / "workflows"
        
        class EmptyWorkflow(Workflow):
            def build_steps(self) -> List[WorkflowStep]:
                return []
        
        workflow = EmptyWorkflow(
            workflow_id="no_run",
            config={},
            storage_path=storage,
            model_gateway=MagicMock()
        )
        
        assert workflow.get_result() is None


class TestWorkflowEngine:
    """WorkflowEngine 测试"""
    
    def test_engine_creation(self, tmp_path):
        """测试：创建引擎"""
        storage = tmp_path / "engine_storage"
        model_gateway = MagicMock()
        
        engine = WorkflowEngine(storage, model_gateway)
        
        assert engine.storage_path == storage
        assert engine.model_gateway == model_gateway
        assert engine.active_workflows == {}
    
    def test_engine_create_workflow(self, tmp_path):
        """测试：创建工作流"""
        storage = tmp_path / "engine_storage"
        engine = WorkflowEngine(storage, MagicMock())
        
        class TestWorkflow(Workflow):
            def build_steps(self):
                return [WorkflowStep("test")]
        
        workflow = engine.create_workflow(
            TestWorkflow,
            "engine_test",
            {"type": "test"}
        )
        
        assert isinstance(workflow, TestWorkflow)
        assert workflow.workflow_id == "engine_test"
        assert "engine_test" in engine.active_workflows
    
    def test_engine_duplicate_workflow_raises(self, tmp_path):
        """测试：重复工作流ID抛出异常"""
        storage = tmp_path / "engine_storage"
        engine = WorkflowEngine(storage, MagicMock())
        
        class TestWorkflow(Workflow):
            def build_steps(self):
                return [WorkflowStep("test")]
        
        engine.create_workflow(TestWorkflow, "duplicate_test", {})
        
        with pytest.raises(ValueError, match="already exists"):
            engine.create_workflow(TestWorkflow, "duplicate_test", {})
    
    def test_engine_get_workflow(self, tmp_path):
        """测试：获取工作流"""
        storage = tmp_path / "engine_storage"
        engine = WorkflowEngine(storage, MagicMock())
        
        class TestWorkflow(Workflow):
            def build_steps(self):
                return [WorkflowStep("test")]
        
        created = engine.create_workflow(TestWorkflow, "get_test", {})
        retrieved = engine.get_workflow("get_test")
        
        assert retrieved is created
        assert engine.get_workflow("nonexistent") is None
    
    def test_engine_list_workflows(self, tmp_path):
        """测试：列出工作流"""
        storage = tmp_path / "engine_storage"
        engine = WorkflowEngine(storage, MagicMock())
        
        class TestWorkflow(Workflow):
            def build_steps(self):
                return [WorkflowStep("test")]
        
        engine.create_workflow(TestWorkflow, "wf1", {})
        engine.create_workflow(TestWorkflow, "wf2", {})
        
        workflows = engine.list_workflows()
        assert len(workflows) == 2
        ids = [wf["id"] for wf in workflows]
        assert "wf1" in ids
        assert "wf2" in ids
    
    def test_engine_run_workflow(self, tmp_path):
        """测试：运行工作流"""
        storage = tmp_path / "engine_storage"
        engine = WorkflowEngine(storage, MagicMock())
        
        class SuccessStep(WorkflowStep):
            def execute(self, context):
                return {"step": self.name}
        
        class TestWorkflow(Workflow):
            def build_steps(self):
                return [SuccessStep("step1")]
        
        engine.create_workflow(TestWorkflow, "run_test", {})
        result = engine.run_workflow("run_test")
        
        assert result.status == WorkflowStatus.COMPLETED
        assert result.output.get("step") == "step1"
    
    def test_engine_run_nonexistent_raises(self, tmp_path):
        """测试：运行不存在的工作流抛出异常"""
        storage = tmp_path / "engine_storage"
        engine = WorkflowEngine(storage, MagicMock())
        
        with pytest.raises(ValueError, match="not found"):
            engine.run_workflow("nonexistent")
    
    def test_engine_cleanup_workflow(self, tmp_path):
        """测试：清理工作流"""
        storage = tmp_path / "engine_storage"
        engine = WorkflowEngine(storage, MagicMock())
        
        class TestWorkflow(Workflow):
            def build_steps(self):
                return [WorkflowStep("test")]
        
        engine.create_workflow(TestWorkflow, "cleanup_test", {})
        assert "cleanup_test" in engine.active_workflows
        
        cleaned = engine.cleanup_workflow("cleanup_test")
        assert cleaned is True
        assert "cleanup_test" not in engine.active_workflows
        
        # 清理不存在的工作流
        assert engine.cleanup_workflow("nonexistent") is False


class TestWorkflowResult:
    """WorkflowResult 测试"""
    
    def test_result_creation(self):
        """测试：创建结果"""
        started = datetime.now(timezone.utc)
        completed = datetime.now(timezone.utc)
        
        result = WorkflowResult(
            workflow_id="test",
            status=WorkflowStatus.COMPLETED,
            output={"key": "value"},
            error=None,
            started_at=started,
            completed_at=completed,
            duration_seconds=1.5
        )
        
        assert result.workflow_id == "test"
        assert result.status == WorkflowStatus.COMPLETED
        assert result.error is None
        assert result.duration_seconds == 1.5
    
    def test_result_to_dict(self):
        """测试：结果转换为字典"""
        started = datetime(2025, 1, 15, 10, 0, 0)
        completed = datetime(2025, 1, 15, 10, 1, 30)
        
        result = WorkflowResult(
            workflow_id="dict_test",
            status=WorkflowStatus.COMPLETED,
            output={"result": "success"},
            error=None,
            started_at=started,
            completed_at=completed,
            duration_seconds=90
        )
        
        data = result.to_dict()
        assert data["workflow_id"] == "dict_test"
        assert data["status"] == WorkflowStatus.COMPLETED
        assert data["duration_seconds"] == 90
        assert data["started_at"] == "2025-01-15T10:00:00"
        assert data["completed_at"] == "2025-01-15T10:01:30"
    
    def test_result_with_none_completion(self):
        """测试：未完成的结果"""
        started = datetime.now(timezone.utc)
        
        result = WorkflowResult(
            workflow_id="running",
            status=WorkflowStatus.RUNNING,
            output={},
            error=None,
            started_at=started,
            completed_at=None,
            duration_seconds=None
        )
        
        data = result.to_dict()
        assert data["completed_at"] is None
        assert data["duration_seconds"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])