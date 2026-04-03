"""Project Module - 项目管理层

提供研究项目的顶层抽象，管理 Idea→Experiment→Review→Write 的完整生命周期。
"""

from .models import Project, ProjectStatus, ProjectEvent, ReviewVerdict, IterationTarget, ReviewResult
from .storage import ProjectStorage
from .manager import ProjectManager

__all__ = [
    "Project",
    "ProjectStatus",
    "ProjectEvent",
    "ReviewVerdict",
    "IterationTarget",
    "ReviewResult",
    "ProjectStorage",
    "ProjectManager",
]
