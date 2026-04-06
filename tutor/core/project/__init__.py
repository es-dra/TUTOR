"""Project Module - 项目管理层

提供研究项目的顶层抽象，管理 Idea→Experiment→Review→Write 的完整生命周期。
"""

# V2 架构（向后兼容）
from .models import Project, ProjectStatus, ProjectEvent, ReviewVerdict, IterationTarget, ReviewResult
from .storage import ProjectStorage
from .manager import ProjectManager

# V3 架构（新一代）
from .v3_project import (
    Project as V3Project,
    ProjectStatus as V3ProjectStatus,
    ProjectManager as V3ProjectManager,
    RoleMessage,
    MessageType,
    ResearchRole,
    DEFAULT_ROLES,
    get_role_by_id,
)
from .role_orchestrator import RoleOrchestrator, create_role_orchestrator

__all__ = [
    # V2
    "Project",
    "ProjectStatus",
    "ProjectEvent",
    "ReviewVerdict",
    "IterationTarget",
    "ReviewResult",
    "ProjectStorage",
    "ProjectManager",
    # V3
    "V3Project",
    "V3ProjectStatus",
    "V3ProjectManager",
    "RoleMessage",
    "MessageType",
    "ResearchRole",
    "DEFAULT_ROLES",
    "get_role_by_id",
    "RoleOrchestrator",
    "create_role_orchestrator",
]
