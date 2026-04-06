"""
TUTOR v3 - Project核心模块
引入Project概念统一管理所有工作流，支持多角色协作
"""

import uuid
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ProjectStatus(str, Enum):
    """项目状态枚举"""

    IDEA = "idea"
    EXPERIMENT = "experiment"
    WRITING = "writing"
    REVIEW = "review"
    COMPLETED = "completed"
    PAUSED = "paused"


class MessageType(str, Enum):
    """角色消息类型"""

    THINK = "think"
    SPEAK = "speak"
    REACT = "react"
    PROPOSE = "propose"


@dataclass
class ResearchRole:
    """科研角色定义"""

    id: str
    name: str
    emoji: str
    color: str
    persona: str
    goal: str
    model_name: str


# 预定义的科研角色
DEFAULT_ROLES = [
    ResearchRole(
        id="innovator",
        name="创新者",
        emoji="🎨",
        color="#FF6B6B",
        persona="创意无限的研究者，喜欢探索新颖想法和突破性方法",
        goal="提出创新且雄心勃勃的研究想法",
        model_name="gpt-4o",
    ),
    ResearchRole(
        id="skeptic",
        name="质疑者",
        emoji="🔍",
        color="#4ECDC4",
        persona="批判性思考者，挑战假设并识别潜在缺陷",
        goal="批评想法并识别风险或弱点",
        model_name="claude-opus-4-20250414",
    ),
    ResearchRole(
        id="pragmatist",
        name="实践者",
        emoji="🛠️",
        color="#45B7D1",
        persona="务实的研究者，专注于可行性和实施",
        goal="评估可行性并提出实用改进",
        model_name="gemini-2.5-pro",
    ),
    ResearchRole(
        id="expert",
        name="专家",
        emoji="📚",
        color="#96CEB4",
        persona="领域专家，具有深厚的专业知识",
        goal="确保想法基于当前研究并识别相关文献",
        model_name="claude-sonnet-4-20250514",
    ),
    ResearchRole(
        id="synthesizer",
        name="综合者",
        emoji="🔗",
        color="#FFEAA7",
        persona="综合各方观点，形成最终方案",
        goal="整合所有角色的最佳观点，形成一致的方案",
        model_name="gpt-4o",
    ),
]


@dataclass
class RoleMessage:
    """角色消息"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    role_id: str = ""
    content: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    message_type: MessageType = MessageType.SPEAK
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["message_type"] = self.message_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleMessage":
        data = data.copy()
        if "message_type" in data:
            data["message_type"] = MessageType(data["message_type"])
        return cls(**data)


@dataclass
class Project:
    """科研项目 - TUTOR v3核心概念"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "新科研项目"
    description: str = ""
    status: ProjectStatus = ProjectStatus.IDEA
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )

    # 关联的工作流数据
    idea_data: Optional[Dict[str, Any]] = None
    experiment_data: Optional[Dict[str, Any]] = None
    paper_data: Optional[Dict[str, Any]] = None
    review_data: Optional[List[Dict[str, Any]]] = None

    # 角色对话历史
    role_conversations: List[RoleMessage] = field(default_factory=list)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 标签系统（支持归档、收藏、备注等）
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["role_conversations"] = [msg.to_dict() for msg in self.role_conversations]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        data = data.copy()
        if "status" in data:
            data["status"] = ProjectStatus(data["status"])
        if "role_conversations" in data:
            data["role_conversations"] = [
                RoleMessage.from_dict(msg) for msg in data["role_conversations"]
            ]
        # 处理标签字段（向后兼容）
        if "tags" not in data:
            data["tags"] = []
        return cls(**data)

    def get_notes(self) -> str:
        """获取备注"""
        for tag in self.tags:
            if tag.startswith("notes:"):
                return tag[6:]
        return ""

    def is_favorite(self) -> bool:
        """是否收藏"""
        return "favorite" in self.tags

    def is_archived(self) -> bool:
        """是否归档"""
        return "archived" in self.tags

    def update_timestamp(self):
        self.updated_at = datetime.now(timezone.utc).isoformat() + "Z"

    def add_role_message(self, message: RoleMessage):
        """添加角色消息"""
        message.project_id = self.id
        self.role_conversations.append(message)
        self.update_timestamp()

    def set_status(self, status: ProjectStatus):
        """设置项目状态"""
        self.status = status
        self.update_timestamp()


class ProjectManager:
    """项目管理器 - 管理Project的CRUD操作"""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.projects_dir = storage_path / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化SQLite存储后端
        from tutor.core.storage import SQLiteBackend
        self.db_backend = SQLiteBackend(storage_path / "tutor.db")
        self.db_backend.initialize()
        
        # 迁移现有JSON数据到SQLite
        self._migrate_from_json()
        
        logger.info(f"ProjectManager initialized at {self.storage_path}")

    def _migrate_from_json(self):
        """从JSON文件迁移到SQLite"""
        try:
            # 检查是否已经迁移过
            existing_projects = self.db_backend.list("project")
            if existing_projects:
                logger.info("Projects already migrated to SQLite, skipping migration")
                return
            
            # 迁移现有JSON项目
            for project_file in self.projects_dir.glob("*.json"):
                try:
                    with open(project_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    project = Project.from_dict(data)
                    self._save_project_to_db(project)
                    logger.info(f"Migrated project: {project.id} from JSON to SQLite")
                except Exception as e:
                    logger.error(f"Failed to migrate project {project_file}: {e}")
        except Exception as e:
            logger.error(f"Migration failed: {e}")

    def _save_project_to_db(self, project: Project):
        """保存项目到SQLite数据库"""
        project_data = project.to_dict()
        # 提取标签
        tags = project_data.pop('tags', [])
        
        # 保存到SQLite
        from tutor.core.storage import StorageMetadata
        metadata = StorageMetadata(tags=tags, extra={})
        self.db_backend.save(project_data, "project", project.id, metadata)

    def _load_project_from_db(self, project_id: str) -> Optional[Project]:
        """从SQLite数据库加载项目"""
        data = self.db_backend.load("project", project_id)
        if data:
            return Project.from_dict(data)
        return None

    def create_project(self, name: str, description: str = "") -> Project:
        """创建新项目"""
        project = Project(name=name, description=description)
        self._save_project_to_db(project)
        logger.info(f"Created project: {project.id} - {name}")
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        # 优先从SQLite加载
        project = self._load_project_from_db(project_id)
        if project:
            return project
        
        # 向后兼容：从JSON文件加载
        project_path = self.projects_dir / f"{project_id}.json"
        if project_path.exists():
            try:
                with open(project_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                project = Project.from_dict(data)
                # 迁移到SQLite
                self._save_project_to_db(project)
                return project
            except Exception as e:
                logger.error(f"Failed to load project {project_path}: {e}")
        
        logger.warning(f"Project not found: {project_id}")
        return None

    def list_projects(self) -> List[Project]:
        """列出所有项目"""
        projects = []
        
        # 从SQLite加载
        project_records = self.db_backend.list("project")
        for record in project_records:
            try:
                project_data = self.db_backend.load("project", record["id"])
                if project_data:
                    project = Project.from_dict(project_data)
                    # 恢复标签
                    project.tags = record.get("tags", [])
                    projects.append(project)
            except Exception as e:
                logger.error(f"Failed to load project {record['id']}: {e}")
        
        # 按更新时间倒序排列
        projects.sort(key=lambda p: p.updated_at, reverse=True)
        return projects

    def update_project(self, project: Project) -> Project:
        """更新项目"""
        project.update_timestamp()
        self._save_project_to_db(project)
        logger.info(f"Updated project: {project.id}")
        return project

    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        # 从SQLite删除
        deleted = self.db_backend.delete("project", project_id)
        if deleted:
            logger.info(f"Deleted project: {project_id}")
        return deleted

    def update_project_tags(
        self, project_id: str, tags: List[str]
    ) -> Optional[Project]:
        """更新项目标签"""
        project = self.get_project(project_id)
        if not project:
            return None
        project.tags = tags
        project.update_timestamp()
        self._save_project_to_db(project)
        logger.info(f"Updated tags for project {project_id}: {tags}")
        return project

    def list_projects_by_tags(
        self, tags: List[str], match_all: bool = False
    ) -> List[Project]:
        """按标签筛选项目"""
        if not tags:
            return self.list_projects()
        
        # 使用SQLite的标签查询
        project_records = self.db_backend.list("project", filter_tags=tags)
        projects = []
        for record in project_records:
            try:
                project_data = self.db_backend.load("project", record["id"])
                if project_data:
                    project = Project.from_dict(project_data)
                    project.tags = record.get("tags", [])
                    projects.append(project)
            except Exception as e:
                logger.error(f"Failed to load project {record['id']}: {e}")
        
        # 按更新时间倒序排列
        projects.sort(key=lambda p: p.updated_at, reverse=True)
        return projects


def get_role_by_id(role_id: str) -> Optional[ResearchRole]:
    """根据ID获取角色"""
    for role in DEFAULT_ROLES:
        if role.id == role_id:
            return role
    return None
