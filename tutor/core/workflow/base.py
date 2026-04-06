"""TUTOR Workflow Engine - 工作流引擎基础框架

定义工作流的核心抽象接口、状态管理和检查点机制。
"""

import json
import logging
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, TypeVar, Generic

from .retry import RetryPolicy, FailureStrategy, WorkflowRetryManager, RollbackChain

logger = logging.getLogger(__name__)


def _get_token_tracker():
    """延迟导入避免循环依赖"""
    from tutor.core.monitor.token_budget import WorkflowTokenTracker, TokenBudget

    return WorkflowTokenTracker, TokenBudget

def _get_plugin_manager():
    """延迟导入避免循环依赖"""
    from .plugin import get_plugin_manager
    return get_plugin_manager()


class WorkflowPauseError(Exception):
    """工作流暂停异常"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


@dataclass
class OrchestratorDecision:
    """Orchestrator 自主决策记录

    记录工作流执行过程中由系统自主处理的决策，
    用于事后审计和透明度提升。
    """

    timestamp: str
    workflow_id: str
    step_name: str
    decision_type: str  # step_timeout_retry, output_format_repair, tool_fallback, etc.
    anomaly: str  # 异常描述
    decision: str  # 做出的决策
    impact: str  # 影响评估
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkflowStatus(str, Enum):
    """工作流状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CheckpointData:
    """检查点数据

    用于工作流状态持久化和断点续传。
    """

    workflow_id: str
    workflow_type: str
    status: str
    current_step: int
    total_steps: int
    step_name: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error: Optional[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointData":
        """从字典创建

        过滤掉未知字段（如 _crc32），只使用 CheckpointData 定义的字段。
        """
        # 定义 CheckpointData 的有效字段
        valid_fields = {
            "workflow_id",
            "workflow_type",
            "status",
            "current_step",
            "total_steps",
            "step_name",
            "input_data",
            "output_data",
            "error",
            "created_at",
            "updated_at",
        }

        # 只保留有效字段
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)

    def save(self, path: Path) -> None:
        """保存检查点到文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        data_dict = self.to_dict()
        content = json.dumps(data_dict, ensure_ascii=False).encode()
        data_dict["_crc32"] = zlib.crc32(content) & 0xFFFFFFFF
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, indent=2, ensure_ascii=False)
        logger.debug(f"Checkpoint saved: {path}")

    @classmethod
    def load(cls, path: Path) -> "CheckpointData":
        """从文件加载检查点"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # CRC32 校验
        stored_crc = data.get("_crc32")
        if stored_crc:
            del data["_crc32"]
            actual_crc = (
                zlib.crc32(json.dumps(data, ensure_ascii=False).encode()) & 0xFFFFFFFF
            )
            if stored_crc != actual_crc:
                raise ValueError(f"CRC32 mismatch for {path}")
        return cls.from_dict(data)


@dataclass
class WorkflowResult:
    """工作流执行结果"""

    workflow_id: str
    status: str
    output: Dict[str, Any]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    # Orchestrator 决策日志（设计文档建议）
    decision_log: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "workflow_id": self.workflow_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "duration_seconds": self.duration_seconds,
            "decision_log": self.decision_log or [],
        }


T = TypeVar("T")


class WorkflowContext(Generic[T]):
    """工作流上下文

    在工作流执行期间共享状态和资源。
    """

    def __init__(
        self,
        workflow_id: str,
        config: Dict[str, Any],
        storage_path: Path,
        model_gateway: Any,
        broadcaster: Any = None,
    ):
        self.workflow_id = workflow_id
        self.config = config
        self.storage_path = storage_path
        self.model_gateway = model_gateway
        self.broadcaster = broadcaster
        self.checkpoints_dir = storage_path / "checkpoints"
        self.results_dir = storage_path / "results"
        self._state: Dict[str, Any] = {}
        self._current_step = 0
        # Orchestrator 自主决策日志（设计文档建议）
        self._decision_log: List[OrchestratorDecision] = []
        # Token 预算追踪器（设计文档建议）
        self._token_tracker: Optional[Any] = None

    def log_decision(
        self,
        step_name: str,
        decision_type: str,
        anomaly: str,
        decision: str,
        impact: str,
        success: bool = True,
    ) -> None:
        """记录 Orchestrator 自主决策

        Args:
            step_name: 步骤名称
            decision_type: 决策类型（如 step_timeout_retry, tool_fallback）
            anomaly: 异常描述
            decision: 做出的决策
            impact: 影响评估
            success: 决策是否成功
        """
        orch_decision = OrchestratorDecision(
            timestamp=datetime.now(timezone.utc).isoformat() + "Z",
            workflow_id=self.workflow_id,
            step_name=step_name,
            decision_type=decision_type,
            anomaly=anomaly,
            decision=decision,
            impact=impact,
            success=success,
        )
        self._decision_log.append(orch_decision)
        logger.info(
            f"Orchestrator decision logged: {decision_type} at step '{step_name}'"
        )

    def get_decision_log(self) -> List[Dict[str, Any]]:
        """获取所有决策日志"""
        return [d.to_dict() for d in self._decision_log]

    def get_token_tracker(self) -> Any:
        """获取 Token 追踪器（延迟初始化）"""
        if self._token_tracker is None:
            WorkflowTokenTracker, _ = _get_token_tracker()
            self._token_tracker = WorkflowTokenTracker()
        return self._token_tracker

    def get_token_budget_summary(self) -> Dict[str, Any]:
        """获取 Token 预算摘要"""
        tracker = self.get_token_tracker()
        return tracker.get_budget().get_summary()

    def get_checkpoint_path(self, step: int) -> Path:
        """获取检查点文件路径"""
        return self.checkpoints_dir / f"step_{step:04d}.json"

    def get_latest_checkpoint(self) -> Optional[CheckpointData]:
        """获取最新的检查点（支持校验和自动修复）"""
        if not self.checkpoints_dir.exists():
            return None

        checkpoints = sorted(self.checkpoints_dir.glob("step_*.json"))
        if not checkpoints:
            return None

        # 从最新到最旧遍历，尝试加载有效的检查点
        for checkpoint_path in reversed(checkpoints):
            try:
                # 使用验证器加载和修复检查点
                from tutor.core.storage.checkpoint_validation import (
                    validate_checkpoint_file,
                )

                data = validate_checkpoint_file(checkpoint_path, repair=True)

                if data is None:
                    logger.warning(f"Skipping invalid checkpoint: {checkpoint_path}")
                    continue  # 尝试更早的检查点

                return CheckpointData.from_dict(data)

            except Exception as e:
                logger.error(f"Failed to load checkpoint {checkpoint_path}: {e}")
                continue

        logger.warning("No valid checkpoints found")
        return None

    def save_checkpoint(
        self,
        step: int,
        step_name: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        error: Optional[str] = None,
    ) -> CheckpointData:
        """保存检查点"""
        checkpoint = CheckpointData(
            workflow_id=self.workflow_id,
            workflow_type=self.config.get("type", "unknown"),
            status=WorkflowStatus.RUNNING if error is None else WorkflowStatus.FAILED,
            current_step=step,
            total_steps=self.config.get("steps", 0),
            step_name=step_name,
            input_data=input_data,
            output_data=output_data,
            error=error,
            created_at=datetime.now(timezone.utc).isoformat() + "Z",
            updated_at=datetime.now(timezone.utc).isoformat() + "Z",
        )

        path = self.get_checkpoint_path(step)
        checkpoint.save(path)
        logger.info(f"Checkpoint saved: step {step} ({step_name})")
        return checkpoint

    def get_state(self, key: str, default: Any = None) -> Any:
        """获取状态值"""
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """设置状态值"""
        self._state[key] = value

    def get_all_state(self) -> Dict[str, Any]:
        """获取所有状态"""
        return self._state.copy()

    def update_state(self, updates: Dict[str, Any]) -> None:
        """批量更新状态"""
        self._state.update(updates)


class WorkflowStep(ABC):
    """工作流步骤抽象基类

    每个工作流由多个步骤组成，步骤可以顺序或并行执行。
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"{__name__}.{self.name}")

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        """执行步骤（子类应重写此方法）

        Args:
            context: 工作流上下文

        Returns:
            步骤执行结果数据
        """
        raise NotImplementedError(
            f"Step '{self.name}' does not implement execute(). "
            "Subclasses must override this method."
        )

    def validate(self, context: WorkflowContext) -> List[str]:
        """验证步骤执行条件

        Returns:
            错误消息列表，空表示验证通过
        """
        return []

    def rollback(self, context: WorkflowContext) -> None:
        """回滚步骤（可选实现）"""
        self.logger.warning(f"Rollback not implemented for step: {self.name}")

    def __str__(self) -> str:
        return f"WorkflowStep({self.name})"


class Workflow(ABC):
    """工作流抽象基类

    所有具体工作流（IdeaFlow、ExperimentFlow等）都应继承此类。
    """

    def __init__(
        self,
        workflow_id: str,
        config: Dict[str, Any],
        storage_path: Path,
        model_gateway: Any,
        broadcaster: Any = None,
    ):
        self.workflow_id = workflow_id
        self.config = config
        self.storage_path = storage_path
        self.model_gateway = model_gateway
        self.context = WorkflowContext(
            workflow_id=workflow_id,
            config=config,
            storage_path=storage_path,
            model_gateway=model_gateway,
            broadcaster=broadcaster,
        )
        self.steps: List[WorkflowStep] = []
        self._current_step_index = 0
        self._result: Optional[WorkflowResult] = None
        self.logger = logging.getLogger(f"{__name__}.{self.workflow_id}")

        # 可靠性: 重试与回滚
        self.failure_strategy = config.get("on_failure", "stop")
        self.retry_policy = RetryPolicy(**config.get("retry", {}))
        self._rollback_chain = RollbackChain()
        self._retry_manager = WorkflowRetryManager()

        # 监控（V3新增）
        self._monitor = None
        self._monitor_config = config.get("monitor", {})

    @abstractmethod
    def build_steps(self) -> List[WorkflowStep]:
        """构建工作流步骤列表

        Returns:
            步骤列表，按执行顺序排列
        """
        pass

    def initialize(self) -> None:
        """初始化工作流"""
        self.steps = self.build_steps()
        self.logger.info(f"Workflow initialized with {len(self.steps)} steps")

        # 尝试恢复之前的检查点
        latest_checkpoint = self.context.get_latest_checkpoint()
        if latest_checkpoint and latest_checkpoint.status != WorkflowStatus.FAILED:
            # 检查点记录的是已完成的步骤索引
            # 如果是 PAUSED 状态（暂停等待审批），需要重试当前步骤
            # 否则恢复时从下一步开始
            if latest_checkpoint.status == WorkflowStatus.PAUSED:
                self._current_step_index = latest_checkpoint.current_step
                self.logger.info(
                    f"Resuming PAUSED workflow from step {self._current_step_index}"
                )
            else:
                self._current_step_index = latest_checkpoint.current_step + 1
                self.logger.info(f"Resuming from step {self._current_step_index}")
            # 恢复步骤输出状态
            if latest_checkpoint.output_data:
                self.context.update_state(latest_checkpoint.output_data)

    def _start_monitoring(self) -> None:
        """启动资源监控"""
        if self._monitor:
            return

        monitor_cfg = self.config.get("monitoring", {})
        if not monitor_cfg.get("enabled", True):
            return

        try:
            from tutor.core.monitor.resource_collector import ResourceMonitor
            from tutor.core.monitor.quotas import QuotaWarning

            def on_quota_warning(warning: QuotaWarning) -> None:
                """处理配额警告"""
                self.logger.warning(f"Quota Warning: {warning.message}")

                if self.context.broadcaster:
                    import asyncio

                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.create_task(
                                self.context.broadcaster.emit(
                                    self.workflow_id, "quota_warning", warning.to_dict()
                                )
                            )
                    except Exception as e:
                        self.logger.error(f"Failed to emit quota warning SSE: {e}")

                if warning.current_value >= 95.0:
                    self.logger.error(
                        f"FATAL Quota Warning: {warning.message}. Requesting workflow PAUSE."
                    )
                    raise WorkflowPauseError(
                        f"Workflow paused due to fatal resource limit: {warning.message}"
                    )

            # 过滤参数，只传递 ResourceMonitor 接受的字段
            valid_args = {
                "interval_seconds": monitor_cfg.get("interval_seconds", 60),
                "gpu_enabled": monitor_cfg.get("gpu_enabled", True),
            }
            self._monitor = ResourceMonitor(**valid_args)
            self._monitor.set_warning_callback(on_quota_warning)
            self._monitor.start()
            self.logger.info("Resource monitor started")
        except ImportError as e:
            self.logger.warning(f"Resource monitor dependencies not available: {e}")
        except Exception as e:
            self.logger.error(f"Failed to start resource monitor: {e}")

    def _stop_monitoring(self) -> None:
        """停止资源监控"""
        if self._monitor and self._monitor.is_running():
            self._monitor.stop()
            self.logger.info("Resource monitor stopped")

    def get_progress(self) -> Dict[str, int]:
        """获取工作流进度

        Returns:
            包含 total_steps, current_step, percent 的字典
        """
        if not self.steps:
            return {"total_steps": 0, "current_step": 0, "percent": 0.0}
        current = self._current_step_index
        total = len(self.steps)
        return {
            "total_steps": total,
            "current_step": current,
            "percent": current / total if total > 0 else 0.0,
        }

    def get_result(self) -> Optional[WorkflowResult]:
        return self._result

    def run(self) -> WorkflowResult:
        """运行工作流（支持重试与回滚）"""
        import asyncio
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # 在没有事件循环的线程中创建一个新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                # 如果已经在事件循环中，使用 create_task
                task = loop.create_task(self.run_async())
                return loop.run_until_complete(task)
            else:
                # 如果不在事件循环中，直接运行
                return asyncio.run(self.run_async())
        except Exception as e:
            self.logger.error(f"Failed to run workflow: {e}")
            raise

    async def run_async(self) -> WorkflowResult:
        """异步运行工作流（支持重试与回滚）"""
        started_at = datetime.now(timezone.utc)
        self.logger.info(f"Starting workflow asynchronously: {self.workflow_id}")

        # 启动资源监控（V3）
        self._start_monitoring()

        strategy_map = {
            "rollback": FailureStrategy.ROLLBACK,
            "stop": FailureStrategy.STOP,
            "continue": FailureStrategy.CONTINUE,
            "pause": FailureStrategy.PAUSE,
        }
        failure_strategy = strategy_map.get(self.failure_strategy, FailureStrategy.STOP)

        try:
            if not self.steps:
                self.initialize()

            while self._current_step_index < len(self.steps):
                step = self.steps[self._current_step_index]
                self.logger.info(
                    f"Executing step {self._current_step_index + 1}/{len(self.steps)}: {step.name}"
                )

                # 更新 context 中的当前步骤索引（供 gate steps 使用）
                self.context._current_step = self._current_step_index

                errors = step.validate(self.context)
                if errors:
                    raise ValueError(f"Step validation failed: {', '.join(errors)}")

                step_input = self.context.get_all_state()

                try:
                    # 异步执行步骤
                    step_output = await self._retry_manager.execute_with_retry_async(
                        step, self.context, self.retry_policy, failure_strategy
                    )
                except Exception as step_err:
                    if failure_strategy == FailureStrategy.ROLLBACK:
                        self.logger.error(
                            f"Step '{step.name}' failed, rolling back: {step_err}"
                        )
                        self._rollback_chain.rollback_all(self.context)
                        raise
                    elif failure_strategy == FailureStrategy.CONTINUE:
                        # 记录 Orchestrator 自主决策（部分结果接受）
                        self.context.log_decision(
                            step_name=step.name,
                            decision_type="partial_result_accept",
                            anomaly=str(step_err),
                            decision="步骤失败但继续执行（CONTINUE策略）",
                            impact="步骤输出为空，已记录错误并继续",
                            success=True,
                        )
                        step_output = {}
                        self.context.save_checkpoint(
                            step=self._current_step_index,
                            step_name=step.name,
                            input_data=step_input,
                            output_data=step_output,
                            error=str(step_err),
                        )
                        self._current_step_index += 1
                        continue
                    elif failure_strategy == FailureStrategy.PAUSE:
                        raise WorkflowPauseError(
                            f"Workflow paused at step '{step.name}'", step_err
                        )
                    else:
                        raise

                self._rollback_chain.add_step(self._current_step_index, step)

                self.context.save_checkpoint(
                    step=self._current_step_index,
                    step_name=step.name,
                    input_data=step_input,
                    output_data=step_output,
                )
                self.context.update_state(step_output)

                # SSE 进度推送
                if self.context.broadcaster:
                    try:
                        await self.context.broadcaster.emit(
                            self.workflow_id, "step", {
                                "step_index": self._current_step_index,
                                "step_name": step.name,
                                "total_steps": len(self.steps),
                                "status": "completed"
                            }
                        )
                    except Exception as e:
                        self.logger.error(f"Failed to emit step progress SSE: {e}")
                self._current_step_index += 1

            status = WorkflowStatus.COMPLETED
            error = None

            result_data = self.context.get_all_state()

            # 停止监控
            self._stop_monitoring()

            result = WorkflowResult(
                workflow_id=self.workflow_id,
                status=status,
                output=result_data,
                error=error,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                duration_seconds=(
                    datetime.now(timezone.utc) - started_at
                ).total_seconds(),
                decision_log=self.context.get_decision_log(),
            )
            self._result = result

            # 记录指标 (V3)
            try:
                from tutor.api.prometheus import get_metrics

                metrics = get_metrics()
                metrics.counter(
                    "tutor_workflow_runs_total",
                    labels={
                        "workflow_type": self.__class__.__name__,
                        "status": status.value,
                    },
                )
                metrics.histogram(
                    "tutor_workflow_duration_seconds",
                    result.duration_seconds,
                    labels={"workflow_type": self.__class__.__name__},
                )
            except Exception as e:
                self.logger.warning(f"Failed to record metrics: {e}")
            return result

        except WorkflowPauseError as pause_err:
            self.logger.warning(f"Workflow PAUSED: {pause_err}")
            self._stop_monitoring()
            return WorkflowResult(
                workflow_id=self.workflow_id,
                status=WorkflowStatus.PAUSED,
                output={},
                error=str(pause_err),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                duration_seconds=(
                    datetime.now(timezone.utc) - started_at
                ).total_seconds(),
                decision_log=self.context.get_decision_log(),
            )
        except Exception as e:
            self.logger.error(f"Workflow failed: {e}")
            self._stop_monitoring()
            
            # 分析错误并生成恢复建议
            try:
                from .error_handling import analyze_error, generate_error_report_dict
                error_analysis = analyze_error(e, self)
                error_report = generate_error_report_dict(e, self)
                
                # 记录错误分析结果
                self.context.log_decision(
                    step_name="error_handling",
                    decision_type="error_analysis",
                    anomaly=str(e),
                    decision=f"错误分类: {error_analysis.error_type.value}",
                    impact=f"严重程度: {error_analysis.severity.value}",
                    success=True,
                )
                
                # 构建错误消息，包含恢复建议
                error_message = f"{str(e)}\n\n恢复建议:\n" + "\n".join([f"- {suggestion}" for suggestion in error_analysis.suggestions])
                
            except Exception as analysis_error:
                self.logger.error(f"Error analysis failed: {analysis_error}")
                error_message = str(e)
                error_report = None
            
            return WorkflowResult(
                workflow_id=self.workflow_id,
                status=WorkflowStatus.FAILED,
                output={},
                error=error_message,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                duration_seconds=(
                    datetime.now(timezone.utc) - started_at
                ).total_seconds(),
                decision_log=self.context.get_decision_log(),
            )


class WorkflowEngine:
    """工作流引擎管理器

    负责工作流的创建、生命周期管理和资源监控集成。
    """

    def __init__(self, storage_path: Path, model_gateway: Any, broadcaster: Any = None):
        self.storage_path = storage_path
        self.model_gateway = model_gateway
        self.broadcaster = broadcaster
        self.active_workflows: Dict[str, Workflow] = {}
        self.logger = logging.getLogger(__name__)

    def create_workflow(
        self, workflow_class: type, workflow_id: str, config: Dict[str, Any]
    ) -> Workflow:
        """创建工作流实例"""
        workflow = workflow_class(
            workflow_id=workflow_id,
            config=config,
            storage_path=self.storage_path,
            model_gateway=self.model_gateway,
            broadcaster=self.broadcaster,
        )
        if workflow_id in self.active_workflows:
            raise ValueError(f"Workflow {workflow_id} already exists")
        self.active_workflows[workflow_id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self.active_workflows.get(workflow_id)

    def list_workflows(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": w.workflow_id,
                "workflow_id": w.workflow_id,
                "type": w.config.get("type", "unknown"),
                "status": w._result.status if w._result else "running",
                "progress": w.get_progress(),
            }
            for w in self.active_workflows.values()
        ]

    def run_workflow(self, workflow_id: str) -> WorkflowResult:
        """运行工作流（首次或恢复）"""
        import asyncio
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # 在没有事件循环的线程中创建一个新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                task = loop.create_task(self.run_workflow_async(workflow_id))
                return loop.run_until_complete(task)
            else:
                return asyncio.run(self.run_workflow_async(workflow_id))
        except Exception as e:
            self.logger.error(f"Failed to run workflow: {e}")
            raise

    async def run_workflow_async(self, workflow_id: str) -> WorkflowResult:
        """异步运行工作流（首次或恢复）"""
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        return await workflow.run_async()

    def resume_workflow(self, workflow_id: str) -> WorkflowResult:
        """恢复暂停的工作流

        前提条件：工作流必须处于 PAUSED 状态（等待审批）。
        调用后会从上一个检查点恢复，继续执行。
        """
        import asyncio
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # 在没有事件循环的线程中创建一个新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                task = loop.create_task(self.resume_workflow_async(workflow_id))
                return loop.run_until_complete(task)
            else:
                return asyncio.run(self.resume_workflow_async(workflow_id))
        except Exception as e:
            self.logger.error(f"Failed to resume workflow: {e}")
            raise

    async def resume_workflow_async(self, workflow_id: str) -> WorkflowResult:
        """异步恢复暂停的工作流"""
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # 检查是否确实处于暂停状态
        if workflow._result and workflow._result.status != WorkflowStatus.PAUSED:
            raise ValueError(
                f"Workflow {workflow_id} is not paused (status: {workflow._result.status}). "
                "Cannot resume."
            )

        # 从检查点恢复并继续执行
        # initialize() 会读取检查点并设置正确的步骤索引
        workflow.initialize()
        return await workflow.run_async()

    def is_workflow_paused(self, workflow_id: str) -> bool:
        """检查工作流是否处于暂停状态"""
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return False
        return (
            workflow._result is not None
            and workflow._result.status == WorkflowStatus.PAUSED
        )

    def cancel_workflow(self, workflow_id: str) -> bool:
        """取消工作流"""
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return False

        if workflow._result and workflow._result.status in [
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        ]:
            return False

        self.logger.warning(f"Cancellation not fully implemented for {workflow_id}")
        return True

    def cleanup_workflow(self, workflow_id: str) -> bool:
        """清理工作流资源"""
        if workflow_id in self.active_workflows:
            del self.active_workflows[workflow_id]
            return True
        return False


# 全局工作流引擎注册表
_workflow_engines: Dict[str, WorkflowEngine] = {}


def get_workflow_engine(workflow_id: str) -> Optional[WorkflowEngine]:
    """根据 workflow_id 获取工作流引擎"""
    return _workflow_engines.get(workflow_id)


def register_workflow_engine(workflow_id: str, engine: WorkflowEngine) -> None:
    """注册工作流引擎"""
    _workflow_engines[workflow_id] = engine
    logger.info(f"Workflow engine registered for {workflow_id}")


def unregister_workflow_engine(workflow_id: str) -> None:
    """注销工作流引擎"""
    _workflow_engines.pop(workflow_id, None)
    logger.debug(f"Workflow engine unregistered for {workflow_id}")
