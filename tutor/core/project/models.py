"""Project Models - 项目数据模型

定义研究项目的核心数据结构和枚举类型。
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any


class ProjectStatus(str, Enum):
    """项目整体状态"""
    DRAFT = "draft"
    IDEA_RUNNING = "idea_running"
    IDEA_COMPLETED = "idea_completed"
    EXPERIMENT_RUNNING = "experiment_running"
    EXPERIMENT_COMPLETED = "experiment_completed"
    REVIEW_RUNNING = "review_running"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"
    WRITE_RUNNING = "write_running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewVerdict(str, Enum):
    """Review 评审结论"""
    ACCEPT = "accept"
    MINOR_REVISION = "minor_revision"
    MAJOR_REVISION = "major_revision"
    REJECT = "reject"


class IterationTarget(str, Enum):
    """Review 不通过时，迭代返回目标"""
    IDEA = "idea"
    EXPERIMENT = "experiment"


class ProjectEvent(str, Enum):
    """触发状态转换的事件"""
    IDEA_COMPLETED = "idea_completed"
    IDEA_APPROVED = "idea_approved"
    IDEA_REJECTED = "idea_rejected"
    EXPERIMENT_COMPLETED = "experiment_completed"
    EXPERIMENT_APPROVED = "experiment_approved"
    EXPERIMENT_REJECTED = "experiment_rejected"
    REVIEW_COMPLETED = "review_completed"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"
    WRITE_COMPLETED = "write_completed"
    ITERATION_REQUESTED = "iteration_requested"
    CANCELLED = "cancelled"


@dataclass
class ReviewResult:
    """Review 阶段评审结果"""
    overall_score: float = 0.0
    scores: Dict[str, float] = field(default_factory=dict)
    verdict: ReviewVerdict = ReviewVerdict.REJECT
    summary: str = ""
    feedback: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "overall_score": self.overall_score,
            "scores": self.scores,
            "verdict": self.verdict.value if isinstance(self.verdict, Enum) else self.verdict,
            "summary": self.summary,
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewResult":
        """从字典创建"""
        verdict = data.get("verdict", "reject")
        if isinstance(verdict, str):
            verdict = ReviewVerdict(verdict)
        return cls(
            overall_score=data.get("overall_score", 0.0),
            scores=data.get("scores", {}),
            verdict=verdict,
            summary=data.get("summary", ""),
            feedback=data.get("feedback", ""),
        )


@dataclass
class Project:
    """研究项目 - 顶层聚合根

    整个项目的生命周期管理器，包含四个工作流的运行状态。
    """
    project_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""

    # 状态机
    status: ProjectStatus = ProjectStatus.DRAFT

    # 四个工作流的 Run IDs
    idea_run_id: Optional[str] = None
    experiment_run_id: Optional[str] = None
    review_run_id: Optional[str] = None
    write_run_id: Optional[str] = None

    # 审批 Gate 状态
    idea_approval_id: Optional[str] = None
    experiment_approval_id: Optional[str] = None

    # Review 结果
    current_review_result: Optional[ReviewResult] = None
    review_history: List[ReviewResult] = field(default_factory=list)

    # 迭代状态
    iteration_count: int = 0
    iteration_target: Optional[IterationTarget] = None

    # 共享数据
    papers: List[Dict[str, Any]] = field(default_factory=list)
    validated_papers: List[Dict[str, Any]] = field(default_factory=list)
    ideas: List[Dict[str, Any]] = field(default_factory=list)
    selected_idea: Optional[Dict[str, Any]] = None
    experiment_report: Optional[Dict[str, Any]] = None

    # 评审阈值配置
    review_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "overall_score": 0.7,
        "innovation": 0.6,
        "feasibility": 0.6,
        "significance": 0.5,
    })

    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "user"

    # 迭代限制
    max_iterations: int = 3

    def get_current_phase(self) -> str:
        """获取当前所处阶段"""
        if self.status.value.startswith("idea"):
            return "idea"
        elif self.status.value.startswith("experiment"):
            return "experiment"
        elif self.status.value.startswith("review"):
            return "review"
        elif self.status.value.startswith("write"):
            return "write"
        return "unknown"

    def can_iterate(self) -> bool:
        """判断是否还能迭代"""
        return self.iteration_count < self.max_iterations

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
        data = asdict(self)
        # 转换枚举为字符串
        data["status"] = self.status.value if isinstance(self.status, Enum) else self.status
        data["iteration_target"] = (
            self.iteration_target.value if isinstance(self.iteration_target, Enum) else self.iteration_target
        )
        if self.current_review_result:
            data["current_review_result"] = self.current_review_result.to_dict()
        data["review_history"] = [r.to_dict() if isinstance(r, ReviewResult) else r for r in self.review_history]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        """从字典创建"""
        # 转换状态字符串为枚举
        if "status" in data and isinstance(data["status"], str):
            try:
                data["status"] = ProjectStatus(data["status"])
            except ValueError:
                data["status"] = ProjectStatus.DRAFT

        # 转换迭代目标
        if "iteration_target" in data and data["iteration_target"]:
            try:
                data["iteration_target"] = IterationTarget(data["iteration_target"])
            except ValueError:
                data["iteration_target"] = None

        # 转换 Review 结果
        if "current_review_result" in data and data["current_review_result"]:
            data["current_review_result"] = ReviewResult.from_dict(data["current_review_result"])

        # 转换 Review 历史
        if "review_history" in data:
            data["review_history"] = [
                ReviewResult.from_dict(r) if isinstance(r, dict) else r
                for r in data["review_history"]
            ]

        return cls(**data)


# ============ 状态转换表 ============

class StateMachine:
    """项目状态机"""

    # 状态转换表: (当前状态, 事件) -> 新状态
    TRANSITIONS: Dict[tuple, str] = {
        # Idea 流程
        (ProjectStatus.DRAFT, ProjectEvent.IDEA_COMPLETED): ProjectStatus.IDEA_RUNNING.value,
        (ProjectStatus.IDEA_RUNNING, ProjectEvent.IDEA_COMPLETED): ProjectStatus.IDEA_COMPLETED.value,
        (ProjectStatus.IDEA_RUNNING, ProjectEvent.IDEA_APPROVED): ProjectStatus.EXPERIMENT_RUNNING.value,
        (ProjectStatus.IDEA_COMPLETED, ProjectEvent.IDEA_APPROVED): ProjectStatus.EXPERIMENT_RUNNING.value,
        (ProjectStatus.IDEA_COMPLETED, ProjectEvent.IDEA_REJECTED): ProjectStatus.IDEA_RUNNING.value,

        # Experiment 流程
        (ProjectStatus.EXPERIMENT_RUNNING, ProjectEvent.EXPERIMENT_COMPLETED): ProjectStatus.EXPERIMENT_COMPLETED.value,
        (ProjectStatus.EXPERIMENT_RUNNING, ProjectEvent.EXPERIMENT_APPROVED): ProjectStatus.REVIEW_RUNNING.value,
        (ProjectStatus.EXPERIMENT_COMPLETED, ProjectEvent.EXPERIMENT_APPROVED): ProjectStatus.REVIEW_RUNNING.value,
        (ProjectStatus.EXPERIMENT_COMPLETED, ProjectEvent.EXPERIMENT_REJECTED): ProjectStatus.EXPERIMENT_RUNNING.value,

        # Review 流程
        (ProjectStatus.REVIEW_RUNNING, ProjectEvent.REVIEW_COMPLETED): ProjectStatus.REVIEW_APPROVED.value,
        (ProjectStatus.REVIEW_APPROVED, ProjectEvent.REVIEW_APPROVED): ProjectStatus.WRITE_RUNNING.value,
        (ProjectStatus.REVIEW_APPROVED, ProjectEvent.REVIEW_REJECTED): ProjectStatus.REVIEW_REJECTED.value,

        # Write 流程
        (ProjectStatus.WRITE_RUNNING, ProjectEvent.WRITE_COMPLETED): ProjectStatus.COMPLETED.value,

        # 取消
        (ProjectStatus.DRAFT, ProjectEvent.CANCELLED): ProjectStatus.CANCELLED.value,
        (ProjectStatus.IDEA_RUNNING, ProjectEvent.CANCELLED): ProjectStatus.CANCELLED.value,
        (ProjectStatus.IDEA_COMPLETED, ProjectEvent.CANCELLED): ProjectStatus.CANCELLED.value,
        (ProjectStatus.EXPERIMENT_RUNNING, ProjectEvent.CANCELLED): ProjectStatus.CANCELLED.value,
        (ProjectStatus.EXPERIMENT_COMPLETED, ProjectEvent.CANCELLED): ProjectStatus.CANCELLED.value,
        (ProjectStatus.REVIEW_RUNNING, ProjectEvent.CANCELLED): ProjectStatus.CANCELLED.value,
        (ProjectStatus.REVIEW_RUNNING, ProjectEvent.REVIEW_REJECTED): ProjectStatus.REVIEW_REJECTED.value,
        (ProjectStatus.WRITE_RUNNING, ProjectEvent.CANCELLED): ProjectStatus.CANCELLED.value,
    }

    @classmethod
    def can_transition(cls, current: ProjectStatus, event: ProjectEvent) -> bool:
        """检查是否可以执行转换"""
        return (current.value, event.value) in cls.TRANSITIONS

    @classmethod
    def get_next_status(cls, current: ProjectStatus, event: ProjectEvent) -> Optional[ProjectStatus]:
        """获取下一状态"""
        key = (current.value, event.value)
        next_str = cls.TRANSITIONS.get(key)
        if next_str:
            return ProjectStatus(next_str)
        return None
