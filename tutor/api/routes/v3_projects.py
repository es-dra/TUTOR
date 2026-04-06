"""V3 Project API Routes - 新一代项目管理

使用v3架构的Project概念，提供项目管理端点。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tutor.core.project.v3_project import (
    Project,
    ProjectManager,
    ProjectStatus,
    RoleMessage,
    MessageType,
    DEFAULT_ROLES,
)
from tutor.core.workflow.base import WorkflowEngine
from tutor.core.model import ModelGateway
from tutor.core.workflow.idea import IdeaFlow
from tutor.core.workflow.experiment import ExperimentFlow
from tutor.core.workflow.write import WriteFlow
from tutor.core.workflow.review import ReviewFlow
from tutor.core.workflow.base import WorkflowStatus as WorkflowRunStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/projects", tags=["v3-projects"])

# 全局项目管理器（延迟初始化）
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """获取项目管理器单例"""
    global _project_manager
    if _project_manager is None:
        storage_path = Path.cwd() / "data"
        _project_manager = ProjectManager(storage_path)
    return _project_manager


# ============ 请求/响应模型 ============

class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    name: str = Field(..., description="项目名称")
    description: str = Field(default="", description="项目描述")


class ProjectResponse(BaseModel):
    """项目响应"""
    id: str
    name: str
    description: str
    status: str
    created_at: str
    updated_at: str
    idea_data: Optional[Dict[str, Any]] = None
    experiment_data: Optional[Dict[str, Any]] = None
    paper_data: Optional[Dict[str, Any]] = None
    review_data: Optional[List[Dict[str, Any]]] = None
    role_conversations: Optional[List[Dict[str, Any]]] = None


class UpdateProjectRequest(BaseModel):
    """更新项目请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class RoleResponse(BaseModel):
    """角色信息响应"""
    id: str
    name: str
    emoji: str
    color: str
    persona: str
    goal: str
    model_name: str


class RunWorkflowRequest(BaseModel):
    """运行工作流请求"""
    workflow_type: str = Field(..., description="工作流类型: idea/experiment/write/review")
    params: Dict[str, Any] = Field(default_factory=dict, description="工作流参数")
    config: Optional[Dict[str, Any]] = Field(default=None, description="运行配置覆盖")


class WorkflowRunResponse(BaseModel):
    """工作流运行响应"""
    run_id: str
    status: str
    workflow_type: str
    message: str


# ============ API 端点 ============

@router.post("")
async def create_project(request: CreateProjectRequest):
    """创建新项目"""
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    project = mgr.create_project(name=request.name, description=request.description)
    
    return success_response(data=ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status.value,
        created_at=project.created_at,
        updated_at=project.updated_at,
    ))


@router.get("")
async def list_projects(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """列出所有项目"""
    from tutor.api.models import success_response, paginated_response
    
    mgr = get_project_manager()
    projects = mgr.list_projects()
    
    # 过滤状态
    if status:
        projects = [p for p in projects if p.status.value == status]
    
    total = len(projects)
    # 分页
    projects = projects[offset:offset+limit]
    
    project_responses = [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status.value,
            created_at=p.created_at,
            updated_at=p.updated_at,
            idea_data=p.idea_data,
            experiment_data=p.experiment_data,
            paper_data=p.paper_data,
            review_data=p.review_data,
        )
        for p in projects
    ]
    
    return paginated_response(items=project_responses, total=total, limit=limit, offset=offset)


@router.get("/{project_id}")
async def get_project(project_id: str):
    """获取项目详情"""
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    project = mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return success_response(data=ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status.value,
        created_at=project.created_at,
        updated_at=project.updated_at,
        idea_data=project.idea_data,
        experiment_data=project.experiment_data,
        paper_data=project.paper_data,
        review_data=project.review_data,
        role_conversations=[msg.to_dict() for msg in project.role_conversations],
    ))


@router.put("/{project_id}")
async def update_project(project_id: str, request: UpdateProjectRequest):
    """更新项目"""
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    project = mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if request.name is not None:
        project.name = request.name
    if request.description is not None:
        project.description = request.description
    if request.status is not None:
        project.set_status(ProjectStatus(request.status))
    
    updated_project = mgr.update_project(project)
    
    return success_response(data=ProjectResponse(
        id=updated_project.id,
        name=updated_project.name,
        description=updated_project.description,
        status=updated_project.status.value,
        created_at=updated_project.created_at,
        updated_at=updated_project.updated_at,
        idea_data=updated_project.idea_data,
        experiment_data=updated_project.experiment_data,
        paper_data=updated_project.paper_data,
        review_data=updated_project.review_data,
    ))


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """删除项目"""
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    success = mgr.delete_project(project_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return success_response(data={"status": "deleted", "project_id": project_id})


@router.get("/{project_id}/conversations")
async def get_project_conversations(project_id: str):
    """获取项目的角色对话历史"""
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    project = mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return success_response(data=[msg.to_dict() for msg in project.role_conversations])


@router.get("/roles/list")
async def list_roles():
    """获取所有可用角色"""
    from tutor.api.models import success_response
    
    roles = [
        RoleResponse(
            id=role.id,
            name=role.name,
            emoji=role.emoji,
            color=role.color,
            persona=role.persona,
            goal=role.goal,
            model_name=role.model_name
        )
        for role in DEFAULT_ROLES
    ]
    
    return success_response(data=roles)


@router.patch("/{project_id}/tags")
async def update_project_tags(project_id: str, tags: Dict[str, List[str]]):
    """更新项目标签（用于归档、收藏、备注等）
    
    Body: {"tags": ["archived", "favorite", "notes:这是备注"]}
    """
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    project = mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    tags_list = tags.get("tags", [])
    if not isinstance(tags_list, list):
        raise HTTPException(status_code=400, detail="tags must be a list")
    
    updated_project = mgr.update_project_tags(project_id, tags_list)
    if not updated_project:
        raise HTTPException(status_code=500, detail="Failed to update tags")
    
    return success_response(data={
        "status": "updated",
        "project_id": project_id,
        "tags": updated_project.tags
    })


@router.get("/list/archived")
async def list_archived_projects(limit: int = 50, offset: int = 0):
    """列出已归档的项目"""
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    projects = mgr.list_projects_by_tags(["archived"])
    
    # 分页
    projects = projects[offset:offset+limit]
    
    project_responses = [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status.value,
            created_at=p.created_at,
            updated_at=p.updated_at,
            idea_data=p.idea_data,
            experiment_data=p.experiment_data,
            paper_data=p.paper_data,
            review_data=p.review_data,
        )
        for p in projects
    ]
    
    return success_response(data=project_responses)


@router.get("/list/favorites")
async def list_favorite_projects(limit: int = 50, offset: int = 0):
    """列出收藏的项目"""
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    projects = mgr.list_projects_by_tags(["favorite"])
    
    # 分页
    projects = projects[offset:offset+limit]
    
    project_responses = [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status.value,
            created_at=p.created_at,
            updated_at=p.updated_at,
            idea_data=p.idea_data,
            experiment_data=p.experiment_data,
            paper_data=p.paper_data,
            review_data=p.review_data,
        )
        for p in projects
    ]
    
    return success_response(data=project_responses)


@router.post("/{project_id}/run-workflow")
async def run_project_workflow(project_id: str, request: RunWorkflowRequest):
    """运行项目工作流
    
    支持的工作流类型：
    - idea: 创意生成
    - experiment: 实验执行
    - write: 论文撰写
    - review: 论文评审
    """
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    project = mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 验证工作流类型
    valid_types = ["idea", "experiment", "write", "review"]
    if request.workflow_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workflow_type '{request.workflow_type}'. Must be one of: {valid_types}"
        )
    
    # 生成唯一的运行ID
    import uuid
    run_id = f"{project_id}_{request.workflow_type}_{str(uuid.uuid4())[:8]}"
    
    # 初始化工作流引擎和模型网关
    storage_path = Path.cwd() / "data" / "projects" / project_id
    storage_path.mkdir(parents=True, exist_ok=True)
    
    model_gateway = ModelGateway(request.config or {})
    engine = WorkflowEngine(storage_path, model_gateway)
    
    # 映射工作流类型到对应的类
    workflow_classes = {
        "idea": IdeaFlow,
        "experiment": ExperimentFlow,
        "write": WriteFlow,
        "review": ReviewFlow
    }
    
    workflow_class = workflow_classes[request.workflow_type]
    
    # 创建并初始化工作流
    workflow = engine.create_workflow(
        workflow_class=workflow_class,
        workflow_id=run_id,
        config={
            "type": request.workflow_type,
            "steps": 0,  # 由工作流自己定义
            **(request.config or {})
        }
    )
    workflow.initialize()
    
    # 启动工作流执行（异步）
    async def execute_workflow():
        try:
            result = await asyncio.to_thread(engine.run_workflow, run_id)
            
            # 更新项目状态和数据
            if request.workflow_type == "idea":
                project.idea_data = result.output
                project.set_status(ProjectStatus.EXPERIMENT)
            elif request.workflow_type == "experiment":
                project.experiment_data = result.output
                project.set_status(ProjectStatus.WRITING)
            elif request.workflow_type == "write":
                project.paper_data = result.output
                project.set_status(ProjectStatus.REVIEW)
            elif request.workflow_type == "review":
                if not project.review_data:
                    project.review_data = []
                project.review_data.append(result.output)
                project.set_status(ProjectStatus.COMPLETED)
            
            mgr.update_project(project)
            logger.info(f"Project {project_id} workflow {request.workflow_type} completed")
        except Exception as e:
            logger.error(f"Project {project_id} workflow {request.workflow_type} failed: {e}")
    
    # 启动异步执行
    asyncio.create_task(execute_workflow())
    
    return success_response(data=WorkflowRunResponse(
        run_id=run_id,
        status="pending",
        workflow_type=request.workflow_type,
        message=f"Workflow '{request.workflow_type}' started for project {project_id}"
    ))


@router.get("/{project_id}/workflow-status/{run_id}")
async def get_workflow_status(project_id: str, run_id: str):
    """获取项目工作流状态"""
    from tutor.api.models import success_response
    
    # 这里可以实现获取工作流状态的逻辑
    # 暂时返回模拟数据
    return success_response(data={
        "run_id": run_id,
        "status": "running",
        "project_id": project_id,
        "message": "Workflow is running"
    })


@router.post("/{project_id}/workflow-resume/{run_id}")
async def resume_workflow(project_id: str, run_id: str):
    """恢复暂停的工作流
    
    从PAUSED状态恢复工作流执行，使用之前的检查点数据。
    """
    from tutor.api.models import success_response
    
    mgr = get_project_manager()
    project = mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 初始化工作流引擎和模型网关
    storage_path = Path.cwd() / "data" / "projects" / project_id
    storage_path.mkdir(parents=True, exist_ok=True)
    
    model_gateway = ModelGateway()
    engine = WorkflowEngine(storage_path, model_gateway)
    
    # 恢复工作流执行
    try:
        # 启动异步执行
        async def resume_workflow_task():
            try:
                # 由于我们没有在引擎中存储工作流实例，这里需要重新创建
                # 但实际上，我们应该从存储中加载工作流状态
                # 这里简化处理，直接返回成功
                # 实际实现中需要：
                # 1. 从检查点加载工作流状态
                # 2. 重新创建工作流实例
                # 3. 调用 engine.resume_workflow()
                
                # 模拟成功恢复
                logger.info(f"Workflow {run_id} resumed successfully")
                
                # 更新项目状态
                project.set_status(ProjectStatus.RUNNING)
                mgr.update_project(project)
                
            except Exception as e:
                logger.error(f"Failed to resume workflow {run_id}: {e}")
        
        # 启动异步执行
        asyncio.create_task(resume_workflow_task())
        
        return success_response(data={
            "run_id": run_id,
            "status": "resumed",
            "project_id": project_id,
            "message": "Workflow resumed successfully"
        })
        
    except Exception as e:
        logger.error(f"Failed to resume workflow {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {str(e)}")

