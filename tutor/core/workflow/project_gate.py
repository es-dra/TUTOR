"""ProjectGateStep - 项目审批门控步骤

在工作流中插入审批点，暂停等待用户审批。

使用方式：
    from tutor.core.workflow.project_gate import ProjectGateStep

    steps = [
        ...
        ProjectGateStep(
            project_id="xxx",
            phase="idea",
            title="审批创意生成结果"
        ),
        ...
    ]
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from .base import WorkflowStep, WorkflowContext, WorkflowPauseError
from .approval import ApprovalManager, ApprovalStatus, approval_manager

logger = logging.getLogger(__name__)

# 使用 approval.py 中的全局单例
def get_approval_manager() -> ApprovalManager:
    """获取审批管理器单例"""
    return approval_manager


class ProjectGateStep(WorkflowStep):
    """项目审批门控步骤

    工作流在此步骤暂停，等待用户审批后继续。
    审批结果会触发项目状态转换。
    """

    def __init__(
        self,
        project_id: str,
        phase: str,
        title: str,
        description: str = "",
        timeout_seconds: int = 86400,  # 默认 24 小时
    ):
        """初始化审批门控

        Args:
            project_id: 项目 ID
            phase: 阶段 ("idea" 或 "experiment")
            title: 审批标题
            description: 审批描述
            timeout_seconds: 超时时间（秒）
        """
        super().__init__(
            name=f"project_gate_{phase}",
            description=f"Project gate for {phase} phase approval"
        )
        self.project_id = project_id
        self.phase = phase
        self.title = title
        self.description = description
        self.timeout_seconds = timeout_seconds

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行审批门控

        1. 创建审批请求
        2. 保存检查点（状态为 paused）
        3. 抛出暂停异常
        4. 工作流返回 PAUSED 状态
        5. 用户审批后，workflow 会被重新调用，此时跳过此步骤（检查点已保存）

        Raises:
            WorkflowPauseError: 表示需要暂停等待审批
        """
        # 构建审批上下文数据
        context_data = self._build_context_data(context)

        # 创建审批请求
        approval_id = f"{self.project_id}_{self.phase}"

        # 如果审批请求已存在，直接跳过（说明已经审批过了）
        manager = get_approval_manager()
        existing = manager.get_request(approval_id)

        if existing and existing.status != ApprovalStatus.PENDING:
            # 已审批，跳过此步骤
            logger.info(f"Approval {approval_id} already resolved, skipping gate")
            # 返回 ideas 以便被调用方获取
            return {
                "approval_id": approval_id,
                "status": existing.status.value,
                "ideas": context_data.get("ideas", []),
                "validated_papers": context_data.get("validated_papers", []),
            }

        if not existing:
            # 创建新审批请求
            manager.create_request(
                approval_id=approval_id,
                run_id=context.workflow_id,
                title=self.title,
                description=self.description,
                context_data=context_data,
                timeout_seconds=self.timeout_seconds,
            )
            logger.info(f"Created approval request: {approval_id}")

        # 保存检查点（在暂停前），以便恢复
        context.save_checkpoint(
            step=context._current_step,
            step_name=self.name,
            input_data=context_data,
            output_data={"approval_id": approval_id, "waiting_for": "approval"},
        )

        # 抛出暂停异常
        raise WorkflowPauseError(
            f"Workflow paused at {self.phase} gate, waiting for approval: {approval_id}"
        )

    async def execute_async(self, context: WorkflowContext) -> Dict[str, Any]:
        """异步执行审批门控"""
        context_data = self._build_context_data(context)
        approval_id = f"{self.project_id}_{self.phase}"

        manager = get_approval_manager()
        existing = manager.get_request(approval_id)

        if existing and existing.status == ApprovalStatus.PENDING:
            logger.info(f"Reusing existing approval request: {approval_id}")
        else:
            manager.create_request(
                approval_id=approval_id,
                run_id=context.workflow_id,
                title=self.title,
                description=self.description,
                context_data=context_data,
                timeout_seconds=self.timeout_seconds,
            )
            logger.info(f"Created approval request: {approval_id}")

        # 等待审批
        logger.info(f"Waiting for approval: {approval_id}")
        status = await manager.get_request(approval_id).wait()

        if status == ApprovalStatus.APPROVED:
            logger.info(f"Approval granted: {approval_id}")
            return {"approval_id": approval_id, "status": "approved"}
        elif status == ApprovalStatus.REJECTED:
            logger.warning(f"Approval rejected: {approval_id}")
            return {"approval_id": approval_id, "status": "rejected"}
        else:
            logger.warning(f"Approval {status}: {approval_id}")
            return {"approval_id": approval_id, "status": status.value}

    def _build_context_data(self, context: WorkflowContext) -> Dict[str, Any]:
        """从工作流上下文构建审批数据"""
        data = {
            "project_id": self.project_id,
            "phase": self.phase,
            "workflow_id": context.workflow_id,
        }

        # 根据阶段添加不同的上下文数据
        if self.phase == "idea":
            # Note: "ideas" key is not stored in context, actual ideas are in "debate_ideas"
            # from IdeaDebateStep and "evaluated_ideas" from IdeaEvaluationStep
            debate_ideas = context.get_state("debate_ideas", [])
            evaluated_ideas = context.get_state("evaluated_ideas", [])
            validated_papers = context.get_state("validated_papers", [])
            recommended_idea = context.get_state("recommended_idea", {})

            # Use evaluated_ideas if available, otherwise use debate_ideas
            ideas_to_show = evaluated_ideas if evaluated_ideas else debate_ideas
            data["ideas"] = ideas_to_show
            data["debate_ideas"] = debate_ideas
            data["paper_count"] = len(validated_papers)
            data["selected_idea"] = recommended_idea

        elif self.phase == "experiment":
            experiment_plan = context.get_state("experiment_plan", {})
            data["experiment_plan"] = experiment_plan

        return data


def link_approval_to_project(
    project_id: str,
    phase: str,
    approval_id: str,
) -> None:
    """将审批请求链接到项目

    Args:
        project_id: 项目 ID
        phase: 阶段
        approval_id: 审批请求 ID
    """
    from tutor.core.project import ProjectManager, ProjectStorage

    mgr = ProjectManager(ProjectStorage())
    project = mgr.get_project(project_id)
    if project:
        mgr.set_approval_id(project, phase, approval_id)
        logger.info(f"Linked approval {approval_id} to project {project_id} phase {phase}")
