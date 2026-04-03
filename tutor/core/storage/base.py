"""存储后端抽象基类

定义所有存储后端的统一接口。
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict


class StorageError(Exception):
    """存储异常"""
    pass


@dataclass
class StorageMetadata:
    """存储元数据"""
    id: str
    type: str
    created_at: str
    updated_at: str
    tags: List[str] = None
    extra: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.extra is None:
            self.extra = {}


class StorageBackend(ABC):
    """存储后端抽象基类
    
    所有具体存储实现（SQLite、文件系统、云存储）都应继承此类。
    """
    
    @abstractmethod
    def initialize(self) -> None:
        """初始化存储后端"""
        pass
    
    @abstractmethod
    def save(self,
             data: Any,
             resource_type: str,
             resource_id: str,
             metadata: Optional[StorageMetadata] = None) -> str:
        """保存数据
        
        Args:
            data: 要保存的数据
            resource_type: 资源类型（如'workflow', 'paper'）
            resource_id: 资源ID
            metadata: 可选元数据
            
        Returns:
            存储路径或键
        """
        pass
    
    @abstractmethod
    def load(self,
             resource_type: str,
             resource_id: str,
             default: Any = None) -> Optional[Any]:
        """加载数据
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            default: 默认值（如果不存在）
            
        Returns:
            加载的数据或default
        """
        pass
    
    @abstractmethod
    def delete(self, resource_type: str, resource_id: str) -> bool:
        """删除数据
        
        Returns:
            True 如果删除成功，False如果不存在
        """
        pass
    
    @abstractmethod
    def exists(self, resource_type: str, resource_id: str) -> bool:
        """检查数据是否存在"""
        pass
    
    @abstractmethod
    def list(self,
             resource_type: str,
             filter_tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """列出资源
        
        Returns:
            资源列表，每项包含id和metadata
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """关闭存储连接"""
        pass
    
    # 上下文管理器支持
    def __enter__(self):
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class StorageManager:
    """存储管理器
    
    管理多个存储后端，提供统一的API。
    根据配置自动选择合适的后端。
    """
    
    def __init__(self, config: Dict[str, Any], base_path: Path):
        self.config = config
        self.base_path = base_path
        self.backends: Dict[str, StorageBackend] = {}
        self._default_backend: Optional[StorageBackend] = None
        self.logger = logging.getLogger(__name__)
    
    def initialize(self) -> None:
        """初始化所有配置的后端"""
        storage_config = self.config.get("storage", {})
        
        # 初始化SQLite后端（用于元数据）
        sqlite_config = storage_config.get("sqlite", {})
        if sqlite_config.get("enabled", True):
            from .sqlite_backend import SQLiteBackend
            db_path = self.base_path / sqlite_config.get("database", "tutor.db")
            sqlite = SQLiteBackend(db_path)
            sqlite.initialize()
            self.backends["sqlite"] = sqlite
            self.logger.info(f"SQLite backend initialized: {db_path}")
        
        # 初始化文件后端（用于数据）
        file_config = storage_config.get("files", {})
        if file_config.get("enabled", True):
            from .file_backend import FileBackend
            data_path = self.base_path / file_config.get("data_dir", "data")
            file_backend = FileBackend(data_path)
            file_backend.initialize()
            self.backends["files"] = file_backend
            self.logger.info(f"File backend initialized: {data_path}")
        
        # 设置默认后端
        self._default_backend = self.backends.get("files")
    
    def get_backend(self, name: str) -> Optional[StorageBackend]:
        """获取指定后端"""
        return self.backends.get(name)
    
    @property
    def default_backend(self) -> StorageBackend:
        """获取默认后端"""
        if not self._default_backend:
            raise StorageError("No default backend available")
        return self._default_backend
    
    def save(self,
             data: Any,
             resource_type: str,
             resource_id: Optional[str] = None,
             metadata: Optional[Dict[str, Any]] = None,
             backend: Optional[str] = None) -> str:
        """保存数据
        
        Args:
            data: 数据
            resource_type: 资源类型
            resource_id: 资源ID（如为None则自动生成）
            metadata: 元数据
            backend: 指定后端（默认使用default_backend）
            
        Returns:
            资源ID
        """
        target_backend = self.backends.get(backend, self.default_backend)
        
        if resource_id is None:
            resource_id = self._generate_id()
        
        # 转换为StorageMetadata
        meta = None
        if metadata:
            meta = StorageMetadata(
                id=resource_id,
                type=resource_type,
                created_at=datetime.now(timezone.utc).isoformat() + "Z",
                updated_at=datetime.now(timezone.utc).isoformat() + "Z",
                tags=metadata.get("tags", []),
                extra={k: v for k, v in metadata.items() if k not in ['tags']}
            )
        
        return target_backend.save(data, resource_type, resource_id, meta)
    
    def load(self,
             resource_type: str,
             resource_id: str,
             default: Any = None,
             backend: Optional[str] = None) -> Optional[Any]:
        """加载数据"""
        target_backend = self.backends.get(backend, self.default_backend)
        return target_backend.load(resource_type, resource_id, default)
    
    def delete(self,
               resource_type: str,
               resource_id: str,
               backend: Optional[str] = None) -> bool:
        """删除数据"""
        target_backend = self.backends.get(backend, self.default_backend)
        return target_backend.delete(resource_type, resource_id)
    
    def exists(self,
               resource_type: str,
               resource_id: str,
               backend: Optional[str] = None) -> bool:
        """检查存在"""
        target_backend = self.backends.get(backend, self.default_backend)
        return target_backend.exists(resource_type, resource_id)
    
    def list(self,
             resource_type: str,
             filter_tags: Optional[List[str]] = None,
             backend: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出资源"""
        target_backend = self.backends.get(backend, self.default_backend)
        return target_backend.list(resource_type, filter_tags)
    
    def close(self) -> None:
        """关闭所有后端"""
        for name, backend in self.backends.items():
            try:
                backend.close()
                self.logger.debug(f"Closed backend: {name}")
            except Exception as e:
                self.logger.error(f"Error closing backend {name}: {e}")
    
    def _generate_id(self) -> str:
        """生成唯一资源ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def __enter__(self):
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 便捷导入
import logging
from datetime import datetime, timezone

__all__ = [
    'StorageBackend',
    'StorageError',
    'StorageMetadata',
    'StorageManager',
]