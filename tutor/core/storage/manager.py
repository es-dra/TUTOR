"""StorageManager - 统一存储管理器

为 TUTOR 工作流提供高层存储 API，内部同时使用 SQLite（元数据索引）
和 FileBackend（实际数据），对外暴露面向业务的接口。
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import StorageError, StorageMetadata
from .file_backend import FileBackend
from .sqlite_backend import SQLiteBackend

logger = logging.getLogger(__name__)

_WORKFLOW_RESOURCE_TYPE = "workflow"


class StorageManager:
    """面向 TUTOR 业务的存储管理器

    配置示例::

        config = {
            "storage": {
                "database": "sqlite:///path/to/tutor.db",
                "project_dir": "/path/to/projects"
            }
        }
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        storage_cfg = config.get("storage", {})

        # SQLite 用于元数据索引和列表查询
        db_url: str = storage_cfg.get("database", "sqlite:///tutor.db")
        self.sqlite_backend = SQLiteBackend(db_url)

        # FileBackend 用于实际数据存储
        project_dir_str: str = storage_cfg.get("project_dir", "./projects")
        self.project_dir = Path(project_dir_str)
        self.file_backend = FileBackend(self.project_dir)

        self._initialized = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """初始化所有后端"""
        self.sqlite_backend.initialize()
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.file_backend.initialize()
        self._initialized = True
        logger.info(
            f"StorageManager initialized. project_dir={self.project_dir}"
        )

    def close(self) -> None:
        self.sqlite_backend.close()
        self.file_backend.close()
        self._initialized = False

    # ------------------------------------------------------------------
    # 工作流 CRUD
    # ------------------------------------------------------------------

    def _make_resource_id(
        self, workflow_id: str, project_id: Optional[str] = None
    ) -> str:
        """生成存储时的唯一资源 ID（含 project 前缀以实现隔离）"""
        if project_id:
            return f"{project_id}__{workflow_id}"
        return workflow_id

    def save_workflow(
        self,
        workflow_id: str,
        workflow_type: str,
        config: Dict[str, Any],
        result: Dict[str, Any],
        project_id: Optional[str] = None,
    ) -> str:
        """保存工作流数据

        Args:
            workflow_id: 工作流唯一标识
            workflow_type: 工作流类型（如 'IdeaFlow'）
            config: 工作流配置
            result: 工作流执行结果
            project_id: 所属项目 ID（用于隔离）

        Returns:
            实际存储的 resource_id
        """
        if not self._initialized:
            raise StorageError("StorageManager not initialized.")

        resource_id = self._make_resource_id(workflow_id, project_id)
        now = datetime.now(timezone.utc).isoformat() + "Z"

        data = {
            "workflow_id": workflow_id,
            "project_id": project_id,
            "type": result.get("type", workflow_type.lower()),
            "workflow_type": workflow_type,
            "config": config,
            "result": result,
            "status": result.get("status", "completed"),
            "created_at": now,
        }

        # 写文件（实际数据）
        meta = StorageMetadata(
            id=resource_id,
            type=_WORKFLOW_RESOURCE_TYPE,
            created_at=now,
            updated_at=now,
            tags=[workflow_type, project_id or "global"],
            extra={"workflow_type": workflow_type, "project_id": project_id or ""},
        )
        self.file_backend.save(data, _WORKFLOW_RESOURCE_TYPE, resource_id, meta)

        # 写 SQLite（元数据索引）
        self.sqlite_backend.save(data, _WORKFLOW_RESOURCE_TYPE, resource_id, meta)

        logger.debug(f"Saved workflow: {resource_id}")
        return resource_id

    def load_workflow(
        self,
        workflow_id: str,
        project_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """加载工作流数据"""
        if not self._initialized:
            raise StorageError("StorageManager not initialized.")

        resource_id = self._make_resource_id(workflow_id, project_id)
        data = self.file_backend.load(_WORKFLOW_RESOURCE_TYPE, resource_id)
        return data

    def list_workflows(
        self,
        workflow_type: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出工作流

        Args:
            workflow_type: 按类型过滤（如 'IdeaFlow'）
            project_id: 按项目过滤
        """
        if not self._initialized:
            raise StorageError("StorageManager not initialized.")

        filter_tags: Optional[List[str]] = None
        if workflow_type:
            filter_tags = [workflow_type]
        if project_id:
            filter_tags = (filter_tags or []) + [project_id]

        items = self.sqlite_backend.list(_WORKFLOW_RESOURCE_TYPE, filter_tags)
        return items

    def delete_workflow(
        self,
        workflow_id: str,
        project_id: Optional[str] = None,
    ) -> bool:
        """删除工作流"""
        if not self._initialized:
            raise StorageError("StorageManager not initialized.")

        resource_id = self._make_resource_id(workflow_id, project_id)
        ok1 = self.file_backend.delete(_WORKFLOW_RESOURCE_TYPE, resource_id)
        ok2 = self.sqlite_backend.delete(_WORKFLOW_RESOURCE_TYPE, resource_id)
        return ok1 or ok2

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------


    def vacuum(self, retention_days: int = 7) -> int:
        """清理过期工作流数据（默认保留7天）"""
        if not self._initialized:
            raise StorageError("StorageManager not initialized.")
        
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        # 1. 从 SQLite 查找过期资源
        expired_resources = self.sqlite_backend.list_expired(_WORKFLOW_RESOURCE_TYPE, cutoff)
        
        count = 0
        for res in expired_resources:
            resource_id = res['id']
            # 2. 物理删除文件
            self.file_backend.delete(_WORKFLOW_RESOURCE_TYPE, resource_id)
            # 3. 从数据库删除
            self.sqlite_backend.delete(_WORKFLOW_RESOURCE_TYPE, resource_id)
            count += 1
            
        logger.info(f"Vacuum complete: cleaned {count} expired workflows (older than {retention_days} days)")
        return count

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


__all__ = ["StorageManager"]
