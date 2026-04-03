"""Project API Routes

提供项目管理端点：
- POST /api/v1/projects - 创建项目
- GET /api/v1/projects - 列出项目
- GET /api/v1/projects/{project_id} - 获取项目详情
- POST /api/v1/projects/{project_id}/approve - 审批通过
- POST /api/v1/projects/{project_id}/reject - 审批拒绝
- POST /api/v1/projects/{project_id}/iterate - 迭代
- DELETE /api/v1/projects/{project_id} - 删除项目
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tutor.core.project import (
    ProjectManager,
    ProjectStorage,
    Project,
    ProjectStatus,
    ProjectEvent,
    IterationTarget,
    ReviewResult,
    ReviewVerdict,
)
from tutor.core.project.models import StateMachine
from tutor.core.workflow.base import WorkflowEngine, WorkflowStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

# 全局项目管理器（延迟初始化）
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """获取项目管理器单例"""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager


def get_model_gateway_config() -> Dict[str, Any]:
    """从 ProviderConfigManager 获取 ModelGateway 配置

    从 providers.yaml 读取配置，构建 ModelGateway 可用的配置字典。
    支持多 Provider 配置，根据 priority 选择默认 Provider。

    Returns:
        ModelGateway 配置字典，包含 provider, api_key, api_base, models
    """
    from tutor.api.routes.providers import get_config_manager

    mgr = get_config_manager()
    all_configs = mgr.get_all_configs()

    # 找到最高优先级的已启用 Provider
    selected_provider = None
    selected_config = None
    lowest_priority = float('inf')

    for name, config in all_configs.items():
        if config.get("enabled", False) and config.get("api_key"):
            priority = config.get("priority", 999)
            if priority < lowest_priority:
                lowest_priority = priority
                selected_provider = name
                selected_config = config

    if not selected_provider:
        logger.warning("No enabled provider with API key found, using defaults")
        return {}

    api_key = mgr.get_api_key(selected_provider)

    # 构建配置
    config = {
        "provider": selected_provider,
        "api_key": api_key,
        "api_base": selected_config.get("api_base", ""),
        "models": selected_config.get("models", {}),
    }

    logger.info(f"Using provider: {selected_provider} with models: {list(selected_config.get('models', {}).keys())}")
    return config


# ============ 请求/响应模型 ============

class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    name: str = Field(..., description="项目名称")
    description: str = Field(default="", description="项目描述")
    papers: List[str] = Field(default_factory=list, description="论文 URL 或本地路径列表")
    research_direction: Optional[str] = Field(None, description="研究方向")
    review_thresholds: Optional[Dict[str, float]] = Field(None, description="评审阈值配置")


class ProjectSummary(BaseModel):
    """项目摘要"""
    project_id: str
    name: str
    status: str
    current_phase: str
    iteration_count: int
    max_iterations: int
    can_iterate: bool
    created_at: str
    updated_at: str


class IdeaContext(BaseModel):
    """Idea 阶段上下文"""
    paper_count: int = 0
    validated_paper_count: int = 0
    idea_count: int = 0
    ideas: List[Dict[str, Any]] = Field(default_factory=list)


class ExperimentContext(BaseModel):
    """Experiment 阶段上下文"""
    selected_idea: Optional[Dict[str, Any]] = None
    experiment_report: Optional[Dict[str, Any]] = None


class ReviewContext(BaseModel):
    """Review 阶段上下文"""
    current_review_result: Optional[Dict[str, Any]] = None
    review_history: List[Dict[str, Any]] = Field(default_factory=list)
    thresholds: Dict[str, float] = Field(default_factory=dict)


class ProjectDetail(BaseModel):
    """完整项目详情"""
    project_id: str
    name: str
    description: str
    status: str
    current_phase: str

    # Run IDs
    idea_run_id: Optional[str] = None
    experiment_run_id: Optional[str] = None
    review_run_id: Optional[str] = None
    write_run_id: Optional[str] = None

    # 审批状态
    idea_approval_id: Optional[str] = None
    experiment_approval_id: Optional[str] = None

    # 阶段上下文
    idea_context: IdeaContext = Field(default_factory=IdeaContext)
    experiment_context: ExperimentContext = Field(default_factory=ExperimentContext)
    review_context: ReviewContext = Field(default_factory=ReviewContext)

    # 迭代
    iteration_count: int = 0
    iteration_target: Optional[str] = None
    can_iterate: bool = True
    max_iterations: int = 3

    # 状态
    created_at: str
    updated_at: str


class IterationRequest(BaseModel):
    """迭代请求"""
    target: str = Field(..., description="迭代目标: 'idea' 或 'experiment'")
    preserve_previous: bool = Field(True, description="是否保留之前的实验数据")


class ApprovalRequest(BaseModel):
    """审批请求"""
    comment: str = Field(default="", description="审批意见")


# ============ API 端点 ============

@router.post("", response_model=ProjectSummary)
async def create_project(request: CreateProjectRequest) -> ProjectSummary:
    """创建新项目

    创建项目后自动启动 IdeaFlow。
    """
    mgr = get_project_manager()

    project = mgr.create_project(
        name=request.name,
        description=request.description,
        papers=request.papers,
        research_direction=request.research_direction,
        review_thresholds=request.review_thresholds,
    )

    # 自动启动 IdeaFlow
    asyncio.create_task(_start_idea_flow(project.project_id))

    return ProjectSummary(
        project_id=project.project_id,
        name=project.name,
        status=project.status.value,
        current_phase=project.get_current_phase(),
        iteration_count=project.iteration_count,
        max_iterations=project.max_iterations,
        can_iterate=project.can_iterate(),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("", response_model=List[ProjectSummary])
async def list_projects(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> List[ProjectSummary]:
    """列出所有项目"""
    mgr = get_project_manager()
    projects = mgr.list_projects(status=status, limit=limit, offset=offset)

    return [
        ProjectSummary(
            project_id=p.project_id,
            name=p.name,
            status=p.status.value,
            current_phase=p.get_current_phase(),
            iteration_count=p.iteration_count,
            max_iterations=p.max_iterations,
            can_iterate=p.can_iterate(),
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str) -> ProjectDetail:
    """获取项目详情"""
    mgr = get_project_manager()
    project = mgr.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return _build_project_detail(project)


@router.post("/{project_id}/approve", response_model=ProjectSummary)
async def approve_project(
    project_id: str,
    request: ApprovalRequest,
) -> ProjectSummary:
    """审批通过

    1. 找到当前阶段的 paused 工作流
    2. 调用审批管理器的 approve
    3. 恢复工作流执行
    4. 工作流将继续并最终触发下一阶段的转换
    """
    mgr = get_project_manager()
    project = mgr.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 找到当前阶段对应的 run_id
    # 注意：工作流可能在 IDEA_RUNNING 状态时暂停在门控处
    if project.status in (ProjectStatus.IDEA_COMPLETED, ProjectStatus.IDEA_RUNNING):
        run_id = project.idea_run_id
        phase = "idea"
    elif project.status in (ProjectStatus.EXPERIMENT_COMPLETED, ProjectStatus.EXPERIMENT_RUNNING):
        run_id = project.experiment_run_id
        phase = "experiment"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve in status {project.status.value}"
        )

    if not run_id:
        raise HTTPException(status_code=400, detail=f"No run_id for phase {phase}")

    # 1. 调用审批管理器 approve 审批请求
    from tutor.core.workflow.approval import approval_manager
    approval_id = f"{project_id}_{phase}"
    approval_manager.approve(approval_id, by="user", comment=request.comment)

    # 2. 获取工作流引擎并恢复工作流
    from tutor.core.workflow.base import get_workflow_engine, WorkflowStatus
    engine = get_workflow_engine(run_id)

    if engine and engine.is_workflow_paused(run_id):
        # 工作流暂停在门控处，需要先获取 ideas 并转移到项目
        if phase == "idea":
            # 从检查点获取 ideas
            checkpoint = engine.active_workflows[run_id].context.get_latest_checkpoint()
            ideas = []
            validated_papers = []
            if checkpoint and checkpoint.input_data:
                ideas = checkpoint.input_data.get("ideas", [])
                validated_papers = checkpoint.input_data.get("validated_papers", [])

            # 先存储 ideas（调用 on_idea_completed 不会触发状态变更如果已经是 IDEA_RUNNING）
            if ideas or validated_papers:
                project.ideas = ideas
                project.validated_papers = validated_papers
                project.updated_at = datetime.now(timezone.utc).isoformat()
                mgr.storage.update(project)

        # 触发审批通过事件并启动实验流程
        if phase == "idea":
            mgr.trigger_event(project, ProjectEvent.IDEA_APPROVED)
        else:
            mgr.trigger_event(project, ProjectEvent.EXPERIMENT_APPROVED)

        # 恢复暂停的工作流，它将继续执行并最终完成
        asyncio.create_task(_resume_workflow_async(run_id, engine, project_id, phase))
    else:
        # 没有暂停的工作流，说明工作流已完成或尚未启动
        # 直接触发下一阶段
        if project.status == ProjectStatus.IDEA_COMPLETED:
            mgr.trigger_event(project, ProjectEvent.IDEA_APPROVED)
            asyncio.create_task(_start_experiment_flow(project_id))
        else:
            mgr.trigger_event(project, ProjectEvent.EXPERIMENT_APPROVED)
            asyncio.create_task(_start_review_flow(project_id))

    # 重新获取项目状态（可能已改变）
    project = mgr.get_project(project_id)

    return ProjectSummary(
        project_id=project.project_id,
        name=project.name,
        status=project.status.value,
        current_phase=project.get_current_phase(),
        iteration_count=project.iteration_count,
        max_iterations=project.max_iterations,
        can_iterate=project.can_iterate(),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("/{project_id}/reject", response_model=ProjectSummary)
async def reject_project(
    project_id: str,
    request: ApprovalRequest,
) -> ProjectSummary:
    """审批拒绝

    将项目标记为已取消（通常用于终止项目）
    """
    mgr = get_project_manager()
    project = mgr.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    mgr.trigger_event(project, ProjectEvent.CANCELLED)

    return ProjectSummary(
        project_id=project.project_id,
        name=project.name,
        status=project.status.value,
        current_phase=project.get_current_phase(),
        iteration_count=project.iteration_count,
        max_iterations=project.max_iterations,
        can_iterate=project.can_iterate(),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("/{project_id}/iterate", response_model=ProjectSummary)
async def iterate_project(
    project_id: str,
    request: IterationRequest,
) -> ProjectSummary:
    """迭代项目

    当 Review 不通过时调用此接口选择迭代目标并继续。
    """
    mgr = get_project_manager()
    project = mgr.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.REVIEW_REJECTED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot iterate in status {project.status.value}"
        )

    if not project.can_iterate():
        raise HTTPException(
            status_code=400,
            detail=f"Maximum iterations ({project.max_iterations}) reached"
        )

    iteration_target = IterationTarget(request.target)

    # 触发迭代事件
    mgr.trigger_event(project, ProjectEvent.ITERATION_REQUESTED, iteration_target=iteration_target)

    # 启动相应的工作流
    if iteration_target == IterationTarget.IDEA:
        asyncio.create_task(_start_idea_flow(project_id, iteration_context=mgr.prepare_iteration(project, iteration_target, request.preserve_previous)))
    else:
        asyncio.create_task(_start_experiment_flow(project_id, iteration_context=mgr.prepare_iteration(project, iteration_target, request.preserve_previous)))

    return ProjectSummary(
        project_id=project.project_id,
        name=project.name,
        status=project.status.value,
        current_phase=project.get_current_phase(),
        iteration_count=project.iteration_count,
        max_iterations=project.max_iterations,
        can_iterate=project.can_iterate(),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("/{project_id}/select-idea", response_model=ProjectSummary)
async def select_idea(
    project_id: str,
    idea: Dict[str, Any],
) -> ProjectSummary:
    """选择创意

    在 IDEA_COMPLETED 状态下，选择一个创意进行实验。
    """
    mgr = get_project_manager()
    project = mgr.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.IDEA_COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot select idea in status {project.status.value}"
        )

    mgr.select_idea(project, idea)

    return ProjectSummary(
        project_id=project.project_id,
        name=project.name,
        status=project.status.value,
        current_phase=project.get_current_phase(),
        iteration_count=project.iteration_count,
        max_iterations=project.max_iterations,
        can_iterate=project.can_iterate(),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.delete("/{project_id}", response_model=Dict[str, str])
async def delete_project(project_id: str) -> Dict[str, str]:
    """删除项目"""
    mgr = get_project_manager()
    project = mgr.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 只能删除已取消或已完成的项目
    if project.status not in [ProjectStatus.CANCELLED, ProjectStatus.COMPLETED, ProjectStatus.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete project in status {project.status.value}"
        )

    from tutor.core.project.storage import ProjectStorage
    storage = ProjectStorage()
    storage.delete(project_id)

    return {"status": "deleted", "project_id": project_id}


# ============ 辅助函数 ============

def _build_project_detail(project: Project) -> ProjectDetail:
    """构建项目详情"""
    idea_context = IdeaContext(
        paper_count=len(project.papers),
        validated_paper_count=len(project.validated_papers),
        idea_count=len(project.ideas),
        ideas=project.ideas,
    )

    experiment_context = ExperimentContext(
        selected_idea=project.selected_idea,
        experiment_report=project.experiment_report,
    )

    review_context = ReviewContext(
        current_review_result=(
            project.current_review_result.to_dict()
            if project.current_review_result else None
        ),
        review_history=[
            r.to_dict() if isinstance(r, ReviewResult) else r
            for r in project.review_history
        ],
        thresholds=project.review_thresholds,
    )

    return ProjectDetail(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        status=project.status.value,
        current_phase=project.get_current_phase(),

        idea_run_id=project.idea_run_id,
        experiment_run_id=project.experiment_run_id,
        review_run_id=project.review_run_id,
        write_run_id=project.write_run_id,

        idea_approval_id=project.idea_approval_id,
        experiment_approval_id=project.experiment_approval_id,

        idea_context=idea_context,
        experiment_context=experiment_context,
        review_context=review_context,

        iteration_count=project.iteration_count,
        iteration_target=(
            project.iteration_target.value
            if project.iteration_target else None
        ),
        can_iterate=project.can_iterate(),
        max_iterations=project.max_iterations,

        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def _start_idea_flow(project_id: str, iteration_context: Optional[Dict] = None):
    """启动 IdeaFlow（实际执行工作流）"""
    import uuid
    from tutor.core.storage.workflow_runs import RunStorage
    from tutor.core.workflow.idea import IdeaFlow
    from tutor.core.workflow.base import (
        WorkflowEngine,
        register_workflow_engine,
        unregister_workflow_engine,
    )
    from tutor.core.model import ModelGateway
    from pathlib import Path
    import os

    try:
        mgr = get_project_manager()
        project = mgr.get_project(project_id)
        if not project:
            return

        # 创建 RunStorage
        run_storage = RunStorage()

        # 创建工作流 Run ID
        run_id = str(uuid.uuid4())[:8]
        run_storage.create_run(
            run_id=run_id,
            workflow_type="idea",
            params={
                "papers": [p["url"] for p in project.papers],
                "iteration_context": iteration_context,
            },
            config={},
        )

        # 更新项目的 idea_run_id
        mgr.set_run_id(project, "idea", run_id)
        project = mgr.get_project(project_id)

        # 准备存储路径
        storage_path = Path(os.getcwd()) / "test_results" / run_id
        storage_path.mkdir(parents=True, exist_ok=True)

        # 创建并注册工作流引擎
        gateway = ModelGateway(get_model_gateway_config())
        engine = WorkflowEngine(storage_path, gateway)
        register_workflow_engine(run_id, engine)

        # 创建工作流
        workflow = engine.create_workflow(
            IdeaFlow,
            run_id,
            {
                "project_id": project_id,
                "paper_sources": [p["url"] for p in project.papers],
                "iteration_context": iteration_context,
            },
        )

        # 在后台线程中运行工作流
        asyncio.create_task(_run_workflow_and_notify(run_id, engine, project_id, "idea", run_storage))

        logger.info(f"Started IdeaFlow for project {project_id}, run_id={run_id}")

    except Exception as e:
        logger.error(f"Failed to start IdeaFlow for project {project_id}: {e}")


async def _run_workflow_and_notify(
    run_id: str,
    engine: WorkflowEngine,
    project_id: str,
    phase: str,
    run_storage: "RunStorage",
):
    """运行工作流并在完成/暂停时通知项目管理者

    Args:
        run_id: 工作流 Run ID
        engine: 工作流引擎
        project_id: 项目 ID
        phase: 阶段 (idea/experiment/review)
        run_storage: 运行存储
    """
    try:
        from tutor.core.workflow.base import WorkflowStatus, unregister_workflow_engine

        result = await asyncio.to_thread(engine.run_workflow, run_id)

        # 更新运行状态
        run_storage.update_status(
            run_id,
            result.status,
            result=result.output,
            error=result.error,
        )

        logger.info(f"Workflow {run_id} completed with status: {result.status}")

        # 根据结果通知项目管理者
        mgr = get_project_manager()
        project = mgr.get_project(project_id)
        if not project:
            return

        if phase == "idea":
            if result.status == WorkflowStatus.COMPLETED.value:
                # Only call on_idea_completed if project is still in IDEA_COMPLETED.
                # If project has progressed (e.g., due to approval already happening),
                # skip this callback to avoid invalid state transitions.
                current_project = mgr.get_project(project_id)
                if current_project and current_project.status == ProjectStatus.IDEA_COMPLETED:
                    mgr.on_idea_completed(
                        project,
                        ideas=result.output.get("ideas", []),
                        validated_papers=result.output.get("validated_papers", []),
                    )
            elif result.status == WorkflowStatus.PAUSED.value:
                # 暂停在审批门控，不需要额外处理，审批通过后会恢复
                pass
        elif phase == "experiment":
            if result.status == WorkflowStatus.COMPLETED.value:
                # Similar guard for experiment completion
                current_project = mgr.get_project(project_id)
                if current_project and current_project.status == ProjectStatus.EXPERIMENT_COMPLETED:
                    mgr.on_experiment_completed(
                        project,
                        experiment_report=result.output,
                    )
            elif result.status == WorkflowStatus.PAUSED.value:
                pass
        elif phase == "review":
            if result.status == WorkflowStatus.COMPLETED.value:
                from tutor.core.project.models import ReviewResult, ReviewVerdict
                # 从输出中提取评审结果
                review_output = result.output or {}
                scores = review_output.get("scores", {})
                overall_score = review_output.get("overall_score", 0.0)

                # 根据 recommendation 确定 verdict
                recommendation = review_output.get("recommendation", "reject").lower()
                if "accept" in recommendation or "minor" in recommendation:
                    verdict = ReviewVerdict.ACCEPT if "accept" in recommendation else ReviewVerdict.MINOR_REVISION
                elif "major" in recommendation:
                    verdict = ReviewVerdict.MAJOR_REVISION
                else:
                    verdict = ReviewVerdict.REJECT

                review_result = ReviewResult(
                    overall_score=overall_score,
                    scores=scores,
                    verdict=verdict,
                    summary=review_output.get("summary", ""),
                    feedback=review_output.get("feedback", ""),
                )
                mgr.on_review_completed(project, review_result)
            elif result.status == WorkflowStatus.PAUSED.value:
                pass

    except Exception as e:
        logger.error(f"Workflow {run_id} failed: {e}")
        run_storage.update_status(run_id, "failed", error=str(e))
    finally:
        unregister_workflow_engine(run_id)


async def _start_experiment_flow(project_id: str, iteration_context: Optional[Dict] = None):
    """启动 ExperimentFlow（实际执行工作流）"""
    import uuid
    from tutor.core.storage.workflow_runs import RunStorage
    from tutor.core.workflow.experiment import ExperimentFlow
    from tutor.core.workflow.base import (
        WorkflowEngine,
        register_workflow_engine,
        unregister_workflow_engine,
    )
    from tutor.core.model import ModelGateway
    from pathlib import Path
    import os

    try:
        mgr = get_project_manager()
        project = mgr.get_project(project_id)
        if not project:
            return

        run_storage = RunStorage()

        run_id = str(uuid.uuid4())[:8]
        run_storage.create_run(
            run_id=run_id,
            workflow_type="experiment",
            params={
                "selected_idea": project.selected_idea,
                "iteration_context": iteration_context,
            },
            config={},
        )

        # 更新项目的 experiment_run_id
        mgr.set_run_id(project, "experiment", run_id)
        project = mgr.get_project(project_id)

        # 准备存储路径
        storage_path = Path(os.getcwd()) / "test_results" / run_id
        storage_path.mkdir(parents=True, exist_ok=True)

        # 创建并注册工作流引擎
        gateway = ModelGateway(get_model_gateway_config())
        engine = WorkflowEngine(storage_path, gateway)
        register_workflow_engine(run_id, engine)

        # 创建工作流
        workflow = engine.create_workflow(
            ExperimentFlow,
            run_id,
            {
                "project_id": project_id,
                "selected_idea": project.selected_idea,
                "iteration_context": iteration_context,
            },
        )

        # 在后台线程中运行工作流
        asyncio.create_task(_run_workflow_and_notify(run_id, engine, project_id, "experiment", run_storage))

        logger.info(f"Started ExperimentFlow for project {project_id}, run_id={run_id}")

    except Exception as e:
        logger.error(f"Failed to start ExperimentFlow for project {project_id}: {e}")


async def _start_review_flow(project_id: str):
    """启动 ReviewFlow（实际执行工作流）"""
    import uuid
    from tutor.core.storage.workflow_runs import RunStorage
    from tutor.core.workflow.review import ReviewFlow
    from tutor.core.workflow.base import (
        WorkflowEngine,
        register_workflow_engine,
        unregister_workflow_engine,
    )
    from tutor.core.model import ModelGateway
    from pathlib import Path
    import os

    try:
        mgr = get_project_manager()
        project = mgr.get_project(project_id)
        if not project:
            return

        run_storage = RunStorage()

        run_id = str(uuid.uuid4())[:8]
        run_storage.create_run(
            run_id=run_id,
            workflow_type="review",
            params={
                "selected_idea": project.selected_idea,
                "experiment_report": project.experiment_report,
            },
            config={},
        )

        # 更新项目的 review_run_id
        mgr.set_run_id(project, "review", run_id)
        project = mgr.get_project(project_id)

        # 准备存储路径
        storage_path = Path(os.getcwd()) / "test_results" / run_id
        storage_path.mkdir(parents=True, exist_ok=True)

        # 创建并注册工作流引擎
        gateway = ModelGateway(get_model_gateway_config())
        engine = WorkflowEngine(storage_path, gateway)
        register_workflow_engine(run_id, engine)

        # 创建工作流
        workflow = engine.create_workflow(
            ReviewFlow,
            run_id,
            {
                "selected_idea": project.selected_idea,
                "experiment_report": project.experiment_report,
            },
        )

        # 在后台线程中运行工作流
        asyncio.create_task(_run_workflow_and_notify(run_id, engine, project_id, "review", run_storage))

        logger.info(f"Started ReviewFlow for project {project_id}, run_id={run_id}")

    except Exception as e:
        logger.error(f"Failed to start ReviewFlow for project {project_id}: {e}")


async def _resume_workflow_async(run_id: str, engine, project_id: str, phase: str):
    """恢复暂停的工作流并在完成后触发后续流程

    这是一个后台任务，在审批后调用。
    工作流恢复后会继续执行，通过 ProjectGateStep 后完成。
    """
    from tutor.core.storage.workflow_runs import RunStorage
    try:
        # 在线程池中运行，因为 workflow.run() 是同步的
        result = await asyncio.to_thread(engine.resume_workflow, run_id)
        logger.info(f"Resumed workflow {run_id} completed with status: {result.status}")

        # 更新运行状态
        run_storage = RunStorage()
        run_storage.update_status(
            run_id,
            result.status,
            result=result.output,
            error=result.error,
        )

        # 注意：项目状态变更已在 approve_project 中处理
        # 这里只需要处理工作流完成后的必要操作

    except Exception as e:
        logger.error(f"Failed to resume workflow {run_id}: {e}")
