"""Multi-Agent Orchestrator

多智能体编排器，协调多个智能体完成复杂任务。
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from tutor.core.multiagent.base import Agent, AgentMessage, AgentResponse, MessageRole
from tutor.core.multiagent.message_bus import MessageBus

logger = logging.getLogger(__name__)


class WorkflowState(Enum):
    """工作流状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StepResult:
    """步骤结果"""
    step_name: str
    agent_id: str
    response: AgentResponse
    duration_ms: float


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    workflow_id: str
    state: WorkflowState
    steps: List[StepResult] = field(default_factory=list)
    final_messages: List[AgentMessage] = field(default_factory=list)
    error: Optional[str] = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "state": self.state.value,
            "steps": [
                {
                    "step_name": s.step_name,
                    "agent_id": s.agent_id,
                    "success": s.response.success,
                    "error": s.response.error,
                    "duration_ms": s.duration_ms,
                }
                for s in self.steps
            ],
            "final_messages": [m.to_dict() for m in self.final_messages],
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


class AgentOrchestrator:
    """多智能体编排器

    支持定义和执行多智能体协作工作流。

    使用示例：
    ```python
    orchestrator = AgentOrchestrator(workflow_id="debate-1")
    orchestrator.add_agent(innovator_agent)
    orchestrator.add_agent(skeptic_agent)

    # 定义辩论流程
    orchestrator.add_step("generate", source="innovator", targets=["skeptic"])
    orchestrator.add_step("critique", source="skeptic", targets=["innovator"])

    result = await orchestrator.run("What's a good research idea?")
    ```
    """

    def __init__(self, workflow_id: str, message_bus: Optional[MessageBus] = None):
        self.workflow_id = workflow_id
        self.message_bus = message_bus or MessageBus()
        self._agents: Dict[str, Agent] = {}
        self._steps: List[Dict[str, Any]] = []
        self._state = WorkflowState.IDLE
        self._result: Optional[WorkflowResult] = None

    def add_agent(self, agent: Agent) -> "AgentOrchestrator":
        """注册智能体

        Args:
            agent: 智能体实例

        Returns:
            self，支持链式调用
        """
        self._agents[agent.id] = agent
        self.message_bus.register(agent)
        return self

    def add_step(
        self,
        name: str,
        source: str,
        targets: List[str],
        message_builder: Optional[Callable[[Dict[str, Any]], str]] = None,
    ) -> "AgentOrchestrator":
        """添加工作流步骤

        Args:
            name: 步骤名称
            source: 源智能体ID
            targets: 目标智能体ID列表
            message_builder: 可选的消息构建函数

        Returns:
            self，支持链式调用
        """
        self._steps.append({
            "name": name,
            "source": source,
            "targets": targets,
            "message_builder": message_builder,
        })
        return self

    def set_steps(self, steps: List[Dict[str, Any]]) -> "AgentOrchestrator":
        """批量设置步骤"""
        self._steps = steps
        return self

    async def run(self, initial_message: str, context: Optional[Dict[str, Any]] = None) -> WorkflowResult:
        """执行工作流

        Args:
            initial_message: 初始消息内容
            context: 共享上下文

        Returns:
            WorkflowResult: 工作流执行结果
        """
        self._state = WorkflowState.RUNNING
        self._result = WorkflowResult(
            workflow_id=self.workflow_id,
            state=WorkflowState.RUNNING,
        )
        context = context or {}

        logger.info(f"Starting workflow '{self.workflow_id}' with {len(self._agents)} agents")

        try:
            for i, step in enumerate(self._steps):
                step_start = datetime.now(timezone.utc)

                source_id = step["source"]
                targets = step["targets"]
                message_builder = step.get("message_builder")

                source_agent = self._agents.get(source_id)
                if not source_agent:
                    raise ValueError(f"Unknown source agent: {source_id}")

                # 构建消息内容
                if message_builder:
                    content = message_builder(context)
                else:
                    content = initial_message if i == 0 else f"Continue with: {initial_message}"

                # 创建消息
                message = AgentMessage(
                    id=f"{self.workflow_id}-step-{i}",
                    sender=source_id,
                    receivers=set(targets),
                    content=content,
                    role=MessageRole.AGENT,
                    metadata={"step_name": step["name"]},
                )

                # 路由消息
                responses = await self.message_bus.publish(message)

                # 记录步骤结果
                duration_ms = (datetime.now(timezone.utc) - step_start).total_seconds() * 1000

                for target_id in targets:
                    target_agent = self._agents.get(target_id)
                    if target_agent:
                        # 找到对应目标的响应
                        target_response = next(
                            (r for r in responses if r.message.sender == target_id),
                            responses[0] if responses else None,
                        )
                        if target_response:
                            self._result.steps.append(StepResult(
                                step_name=step["name"],
                                agent_id=target_id,
                                response=target_response,
                                duration_ms=duration_ms,
                            ))
                            # 更新上下文
                            if target_response.success:
                                context[f"{target_id}_response"] = target_response.message.content

                logger.info(
                    f"Step {i+1}/{len(self._steps)} '{step['name']}': "
                    f"{sum(1 for r in responses if r.success)}/{len(responses)} succeeded"
                )

            self._state = WorkflowState.COMPLETED
            self._result.state = WorkflowState.COMPLETED
            self._result.completed_at = datetime.now(timezone.utc).isoformat() + "Z"

        except Exception as e:
            logger.error(f"Workflow '{self.workflow_id}' failed: {e}", exc_info=True)
            self._state = WorkflowState.FAILED
            self._result.state = WorkflowState.FAILED
            self._result.error = str(e)

        return self._result

    def get_state(self) -> WorkflowState:
        """获取当前状态"""
        return self._state

    def get_result(self) -> Optional[WorkflowResult]:
        """获取执行结果"""
        return self._result

    def reset(self) -> None:
        """重置工作流"""
        self._state = WorkflowState.IDLE
        self._result = None
        self.message_bus.clear_history()
        for agent in self._agents.values():
            agent.clear_history()
