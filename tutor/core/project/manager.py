"""Project Manager - 项目管理器

管理研究项目的完整生命周期，协调 Idea→Experiment→Review→Write 工作流。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .models import Project, ProjectStatus, ProjectEvent, ReviewVerdict, IterationTarget, ReviewResult, StateMachine
from .storage import ProjectStorage

logger = logging.getLogger(__name__)


class ProjectManager:
    """项目管理器

    协调研究项目的完整生命周期。
    """

    def __init__(self, storage: Optional[ProjectStorage] = None):
        """初始化

        Args:
            storage: 项目存储实例
        """
        self.storage = storage or ProjectStorage()

    def create_project(
        self,
        name: str,
        description: str = "",
        papers: Optional[List[str]] = None,
        research_direction: Optional[str] = None,
        review_thresholds: Optional[Dict[str, float]] = None,
        created_by: str = "user",
    ) -> Project:
        """创建新项目

        Args:
            name: 项目名称
            description: 项目描述
            papers: 论文 URL 或本地路径列表
            research_direction: 研究方向
            review_thresholds: 评审阈值配置
            created_by: 创建者

        Returns:
            创建的项目
        """
        project = Project(
            name=name,
            description=description,
            status=ProjectStatus.IDEA_RUNNING,
            papers=[{"url": p, "source": "user_input"} for p in (papers or [])],
            review_thresholds=review_thresholds or {},
            created_by=created_by,
        )

        if research_direction:
            project.research_direction = research_direction

        self.storage.create(project)
        logger.info(f"Created project {project.project_id}: {name}")

        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        return self.storage.get(project_id)

    def list_projects(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Project]:
        """列出项目"""
        return self.storage.list(status=status, limit=limit, offset=offset)

    def update_project(self, project: Project) -> Project:
        """更新项目"""
        project.updated_at = datetime.now(timezone.utc).isoformat()
        return self.storage.update(project)

    def trigger_event(
        self,
        project: Project,
        event: ProjectEvent,
        **kwargs,
    ) -> Project:
        """触发项目状态转换

        Args:
            project: 项目实例
            event: 触发的事件
            **kwargs: 额外参数

        Returns:
            更新后的项目
        """
        old_status = project.status

        # 处理特殊事件
        if event == ProjectEvent.ITERATION_REQUESTED:
            iteration_target = kwargs.get("iteration_target", IterationTarget.IDEA)
            project.iteration_target = iteration_target
            project.iteration_count += 1

            # 根据迭代目标设置状态
            if iteration_target == IterationTarget.EXPERIMENT:
                project.status = ProjectStatus.EXPERIMENT_RUNNING
            else:
                project.status = ProjectStatus.IDEA_RUNNING

        elif event == ProjectEvent.REVIEW_APPROVED:
            # Review 通过后直接进入 Write
            project.status = ProjectStatus.WRITE_RUNNING

        elif event == ProjectEvent.CANCELLED:
            project.status = ProjectStatus.CANCELLED

        else:
            # 使用状态机转换
            next_status = StateMachine.get_next_status(project.status, event)
            if next_status:
                project.status = next_status
            else:
                logger.warning(f"Invalid transition: {project.status} + {event}")
                return project

        project.updated_at = datetime.now(timezone.utc).isoformat()
        self.storage.update(project)

        logger.info(f"Project {project.project_id}: {old_status.value} -> {project.status.value} ({event.value})")
        return project

    def on_idea_completed(
        self,
        project: Project,
        ideas: List[Dict[str, Any]],
        validated_papers: List[Dict[str, Any]],
    ) -> Project:
        """Idea 工作流完成回调

        Args:
            project: 项目实例
            ideas: 生成的创意列表
            validated_papers: 验证后的文献列表

        Returns:
            更新后的项目
        """
        project.ideas = ideas
        project.validated_papers = validated_papers
        project.updated_at = datetime.now(timezone.utc).isoformat()

        return self.trigger_event(project, ProjectEvent.IDEA_COMPLETED)

    def on_experiment_completed(
        self,
        project: Project,
        experiment_report: Dict[str, Any],
    ) -> Project:
        """Experiment 工作流完成回调

        Args:
            project: 项目实例
            experiment_report: 实验报告

        Returns:
            更新后的项目
        """
        project.experiment_report = experiment_report
        return self.trigger_event(project, ProjectEvent.EXPERIMENT_COMPLETED)

    def on_review_completed(
        self,
        project: Project,
        review_result: ReviewResult,
    ) -> Project:
        """Review 工作流完成回调

        Args:
            project: 项目实例
            review_result: 评审结果

        Returns:
            更新后的项目
        """
        project.current_review_result = review_result
        project.review_history.append(review_result)

        # 判断是否通过
        if self._is_review_passed(review_result, project.review_thresholds):
            return self.trigger_event(project, ProjectEvent.REVIEW_APPROVED)
        else:
            return self.trigger_event(project, ProjectEvent.REVIEW_REJECTED)

    def on_write_completed(self, project: Project) -> Project:
        """Write 工作流完成回调"""
        return self.trigger_event(project, ProjectEvent.WRITE_COMPLETED)

    def _is_review_passed(
        self,
        result: ReviewResult,
        thresholds: Dict[str, float],
    ) -> bool:
        """判断 Review 是否通过

        Args:
            result: 评审结果
            thresholds: 阈值配置

        Returns:
            是否通过
        """
        # 检查各维度
        for dim, threshold in thresholds.items():
            if dim == "overall_score":
                continue
            score = result.scores.get(dim, 0.0)
            if score < threshold:
                return False

        # 检查总体评分
        overall_threshold = thresholds.get("overall_score", 0.7)
        if result.overall_score < overall_threshold:
            return False

        # 检查 verdict
        if result.verdict in [ReviewVerdict.ACCEPT, ReviewVerdict.MINOR_REVISION]:
            return True

        return False

    def prepare_iteration(
        self,
        project: Project,
        target: IterationTarget,
        preserve_previous: bool = True,
    ) -> Dict[str, Any]:
        """准备迭代上下文

        Args:
            project: 项目实例
            target: 迭代目标
            preserve_previous: 是否保留之前的实验数据

        Returns:
            传递给下一个工作流的上下文
        """
        context = {
            "project_id": project.project_id,
            "iteration": project.iteration_count + 1,
            "target": target.value,
        }

        if target == IterationTarget.IDEA:
            context["papers"] = project.papers
            context["validated_papers"] = project.validated_papers
            context["previous_ideas"] = project.ideas
            context["previous_selected_idea"] = project.selected_idea
            if project.current_review_result:
                context["review_feedback"] = project.current_review_result.feedback

        elif target == IterationTarget.EXPERIMENT:
            context["selected_idea"] = project.selected_idea
            context["previous_experiment"] = project.experiment_report
            if project.current_review_result:
                context["review_feedback"] = project.current_review_result.feedback

            if preserve_previous and project.experiment_report:
                context["previous_metrics"] = project.experiment_report.get("metrics", {})
                context["previous_artifacts"] = project.experiment_report.get("artifacts", [])

        return context

    def set_run_id(
        self,
        project: Project,
        phase: str,
        run_id: str,
    ) -> Project:
        """设置工作流 Run ID

        Args:
            project: 项目实例
            phase: 阶段 (idea, experiment, review, write)
            run_id: 工作流 Run ID

        Returns:
            更新后的项目
        """
        if phase == "idea":
            project.idea_run_id = run_id
        elif phase == "experiment":
            project.experiment_run_id = run_id
        elif phase == "review":
            project.review_run_id = run_id
        elif phase == "write":
            project.write_run_id = run_id

        return self.update_project(project)

    def set_approval_id(
        self,
        project: Project,
        phase: str,
        approval_id: str,
    ) -> Project:
        """设置审批 ID

        Args:
            project: 项目实例
            phase: 阶段 (idea, experiment)
            approval_id: 审批 ID

        Returns:
            更新后的项目
        """
        if phase == "idea":
            project.idea_approval_id = approval_id
        elif phase == "experiment":
            project.experiment_approval_id = approval_id

        return self.update_project(project)

    def select_idea(
        self,
        project: Project,
        idea: Dict[str, Any],
    ) -> Project:
        """选择创意

        Args:
            project: 项目实例
            idea: 选中的创意

        Returns:
            更新后的项目
        """
        project.selected_idea = idea
        return self.update_project(project)
