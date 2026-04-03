"""Project Storage - 项目持久化存储

使用 SQLite 数据库持久化项目记录。
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ProjectStorage:
    """项目存储

    使用 SQLite 数据库持久化项目记录。
    """

    def __init__(self, db_path: str = "data/tutor_projects.db"):
        """初始化存储

        Args:
            db_path: 数据库路径
        """
        if isinstance(db_path, str) and db_path.startswith("sqlite:///"):
            db_path = db_path[len("sqlite:///"):]
        self.db_path = Path(db_path)
        self._conn = None
        self._lock = threading.Lock()

    @contextmanager
    def _get_conn(self):
        """获取数据库连接"""
        with self._lock:
            if self._conn is None:
                import sqlite3
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._init_tables()
            try:
                yield self._conn
            finally:
                pass

    def _init_tables(self) -> None:
        """初始化数据表"""
        cursor = self._conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'draft',

            -- 四个工作流 Run IDs
            idea_run_id TEXT,
            experiment_run_id TEXT,
            review_run_id TEXT,
            write_run_id TEXT,

            -- 审批 IDs
            idea_approval_id TEXT,
            experiment_approval_id TEXT,

            -- Review 结果（JSON）
            current_review_result TEXT,
            review_history TEXT,

            -- 迭代状态
            iteration_count INTEGER DEFAULT 0,
            iteration_target TEXT,

            -- 共享数据（JSON）
            papers TEXT,
            validated_papers TEXT,
            ideas TEXT,
            selected_idea TEXT,
            experiment_report TEXT,

            -- 阈值配置
            review_thresholds TEXT,

            -- 元数据
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT,
            max_iterations INTEGER DEFAULT 3
        )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at)")

        self._conn.commit()

    def create(self, project: "Project") -> "Project":
        """创建新项目

        Args:
            project: Project 实例

        Returns:
            创建的项目
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            data = project.to_dict()

            # JSON 序列化复杂字段
            json_fields = [
                "current_review_result", "review_history", "papers",
                "validated_papers", "ideas", "selected_idea",
                "experiment_report", "review_thresholds"
            ]
            for field in json_fields:
                if data.get(field) is not None and not isinstance(data[field], str):
                    data[field] = json.dumps(data[field], ensure_ascii=False)

            cursor.execute("""
                INSERT INTO projects (
                    project_id, name, description, status,
                    idea_run_id, experiment_run_id, review_run_id, write_run_id,
                    idea_approval_id, experiment_approval_id,
                    current_review_result, review_history,
                    iteration_count, iteration_target,
                    papers, validated_papers, ideas, selected_idea, experiment_report,
                    review_thresholds,
                    created_at, updated_at, created_by, max_iterations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["project_id"], data["name"], data["description"], data["status"],
                data.get("idea_run_id"), data.get("experiment_run_id"),
                data.get("review_run_id"), data.get("write_run_id"),
                data.get("idea_approval_id"), data.get("experiment_approval_id"),
                data.get("current_review_result"), data.get("review_history"),
                data.get("iteration_count", 0), data.get("iteration_target"),
                data.get("papers"), data.get("validated_papers"),
                data.get("ideas"), data.get("selected_idea"),
                data.get("experiment_report"), data.get("review_thresholds"),
                data["created_at"], data["updated_at"], data.get("created_by", "user"),
                data.get("max_iterations", 3),
            ))
            conn.commit()

        return project

    def get(self, project_id: str) -> Optional["Project"]:
        """获取项目

        Args:
            project_id: 项目 ID

        Returns:
            Project 实例或 None
        """
        from .models import Project

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_project(row)

    def update(self, project: "Project") -> "Project":
        """更新项目

        Args:
            project: Project 实例

        Returns:
            更新后的项目
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            data = project.to_dict()

            # 更新时间戳
            data["updated_at"] = datetime.now(timezone.utc).isoformat()

            # JSON 序列化复杂字段
            json_fields = [
                "current_review_result", "review_history", "papers",
                "validated_papers", "ideas", "selected_idea",
                "experiment_report", "review_thresholds"
            ]
            for field in json_fields:
                if data.get(field) is not None and not isinstance(data[field], str):
                    data[field] = json.dumps(data[field], ensure_ascii=False)

            cursor.execute("""
                UPDATE projects SET
                    name = ?, description = ?, status = ?,
                    idea_run_id = ?, experiment_run_id = ?, review_run_id = ?, write_run_id = ?,
                    idea_approval_id = ?, experiment_approval_id = ?,
                    current_review_result = ?, review_history = ?,
                    iteration_count = ?, iteration_target = ?,
                    papers = ?, validated_papers = ?, ideas = ?, selected_idea = ?,
                    experiment_report = ?, review_thresholds = ?,
                    updated_at = ?, max_iterations = ?
                WHERE project_id = ?
            """, (
                data["name"], data["description"], data["status"],
                data.get("idea_run_id"), data.get("experiment_run_id"),
                data.get("review_run_id"), data.get("write_run_id"),
                data.get("idea_approval_id"), data.get("experiment_approval_id"),
                data.get("current_review_result"), data.get("review_history"),
                data.get("iteration_count", 0), data.get("iteration_target"),
                data.get("papers"), data.get("validated_papers"),
                data.get("ideas"), data.get("selected_idea"),
                data.get("experiment_report"), data.get("review_thresholds"),
                data["updated_at"], data.get("max_iterations", 3),
                data["project_id"],
            ))
            conn.commit()

        return project

    def list(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List["Project"]:
        """列出项目

        Args:
            status: 按状态筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            Project 列表
        """
        from .models import Project

        with self._get_conn() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute(
                    "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset)
                )
            else:
                cursor.execute(
                    "SELECT * FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                )

            rows = cursor.fetchall()
            return [self._row_to_project(row) for row in rows]

    def delete(self, project_id: str) -> bool:
        """删除项目

        Args:
            project_id: 项目 ID

        Returns:
            是否删除成功
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_project(self, row: "sqlite3.Row") -> "Project":
        """将数据库行转换为 Project 实例"""
        from .models import Project

        data = dict(row)

        # 解析 JSON 字段
        json_fields = [
            "current_review_result", "review_history", "papers",
            "validated_papers", "ideas", "selected_idea",
            "experiment_report", "review_thresholds"
        ]
        for field in json_fields:
            if data.get(field) and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except json.JSONDecodeError:
                    data[field] = None

        return Project.from_dict(data)
