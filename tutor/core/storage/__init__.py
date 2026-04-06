"""TUTOR Storage Manager - 数据存储管理

提供统一的数据持久化接口，支持：
- SQLite元数据存储
- JSON文件系统存储
- 抽象存储层（便于扩展）
"""

from .base import StorageBackend, StorageError, StorageMetadata
from .sqlite_backend import SQLiteBackend
from .file_backend import FileBackend
from .manager import StorageManager

__all__ = [
    'StorageBackend',
    'StorageError',
    'StorageMetadata',
    'SQLiteBackend',
    'FileBackend',
    'StorageManager',
]