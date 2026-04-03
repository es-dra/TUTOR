"""SQLite存储后端

存储资源元数据，支持：
- 资源CRUD
- 标签查询
- 全文搜索（后续扩展）
"""

import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import StorageBackend, StorageError, StorageMetadata

logger = logging.getLogger(__name__)


class SQLiteBackend(StorageBackend):
    """SQLite存储后端
    
    表结构：
    - resources: 资源元数据
    - tags: 标签（多对多关系）
    - data_refs: 数据引用（关联其他后端）
    """
    
    def __init__(self, db_path):
        """初始化 SQLite 后端。

        Args:
            db_path: 数据库路径，可以是：
                - Path 对象（直接使用）
                - 字符串路径（如 '/tmp/tutor.db'）
                - SQLite URL 字符串（如 'sqlite:///tmp/tutor.db'）
        """
        if isinstance(db_path, str):
            # 去掉 sqlite:// 或 sqlite:/// 前缀
            if db_path.startswith("sqlite:///"):
                db_path = db_path[len("sqlite:///"):]
            elif db_path.startswith("sqlite://"):
                db_path = db_path[len("sqlite://"):]
            db_path = Path(db_path)
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（供内部和测试访问）"""
        if self.conn is None:
            raise StorageError("Database not initialized. Call initialize() first.")
        return self.conn
    
    def initialize(self) -> None:
        """初始化数据库"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        
        # 创建表
        self._create_tables()
        logger.info(f"SQLite database initialized: {self.db_path}")
    
    def close(self) -> None:
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("SQLite connection closed")
    
    def __del__(self):
        """析构时自动关闭连接，防止 Windows 文件锁"""
        try:
            self.close()
        except Exception:
            pass
    
    def _create_tables(self) -> None:
        """创建数据表"""
        cursor = self.conn.cursor()
        
        # 资源元数据表（含数据 blob）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            backend TEXT NOT NULL DEFAULT 'sqlite',
            data_key TEXT NOT NULL,
            data_blob TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            extra TEXT  -- JSON
        )
        """)
        
        # 标签表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE,
            UNIQUE(resource_id, tag)
        )
        """)
        
        # 索引
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tags_resource ON tags(resource_id)
        """)
        
        self.conn.commit()
    
    def save(self,
             data: Any,
             resource_type: str,
             resource_id: str,
             metadata: Optional[StorageMetadata] = None) -> str:
        """保存资源数据和元数据"""
        cursor = self.conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat() + "Z"
        
        if metadata:
            extra_json = json.dumps(metadata.extra) if metadata.extra else None
            tags = metadata.tags or []
        else:
            extra_json = None
            tags = []
        
        # 将数据序列化为 JSON blob
        try:
            data_blob = json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            data_blob = str(data)
        
        # 检查是否已存在
        cursor.execute(
            "SELECT id FROM resources WHERE id = ?",
            (resource_id,)
        )
        exists = cursor.fetchone() is not None
        
        if exists:
            # 更新
            cursor.execute("""
            UPDATE resources
            SET type = ?, updated_at = ?, extra = ?, data_blob = ?
            WHERE id = ?
            """, (resource_type, now, extra_json, data_blob, resource_id))
            
            # 删除旧标签
            cursor.execute(
                "DELETE FROM tags WHERE resource_id = ?",
                (resource_id,)
            )
        else:
            # 插入
            data_key = resource_id
            
            cursor.execute("""
            INSERT INTO resources (id, type, data_key, data_blob, created_at, updated_at, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (resource_id, resource_type, data_key, data_blob, now, now, extra_json))
        
        # 插入标签
        for tag in tags:
            cursor.execute(
                "INSERT OR IGNORE INTO tags (resource_id, tag) VALUES (?, ?)",
                (resource_id, tag)
            )
        
        self.conn.commit()
        logger.debug(f"Saved resource: {resource_id} ({resource_type})")
        
        return resource_id
    
    def load(self,
             resource_type: str,
             resource_id: str,
             default: Any = None) -> Optional[Any]:
        """加载资源数据（返回原始数据）"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
        SELECT * FROM resources WHERE id = ? AND type = ?
        """, (resource_id, resource_type))
        
        row = cursor.fetchone()
        if not row:
            return default
        
        # 反序列化数据 blob
        data_blob = row['data_blob']
        if data_blob is not None:
            try:
                return json.loads(data_blob)
            except (json.JSONDecodeError, TypeError):
                return data_blob
        
        return default
    
    def delete(self, resource_type: str, resource_id: str) -> bool:
        """删除资源元数据"""
        cursor = self.conn.cursor()
        
        # 先检查是否存在
        cursor.execute(
            "SELECT id FROM resources WHERE id = ? AND type = ?",
            (resource_id, resource_type)
        )
        if not cursor.fetchone():
            return False
        
        # 删除标签（级联应自动处理，但显式删除更安全）
        cursor.execute(
            "DELETE FROM tags WHERE resource_id = ?",
            (resource_id,)
        )
        
        # 删除资源
        cursor.execute(
            "DELETE FROM resources WHERE id = ?",
            (resource_id,)
        )
        
        self.conn.commit()
        logger.debug(f"Deleted resource: {resource_id}")
        
        return True
    
    def exists(self, resource_type: str, resource_id: str) -> bool:
        """检查资源是否存在"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM resources WHERE id = ? AND type = ?",
            (resource_id, resource_type)
        )
        return cursor.fetchone() is not None
    
    def list(self,
             resource_type: str,
             filter_tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """列出资源"""
        cursor = self.conn.cursor()
        
        if filter_tags:
            # 查询包含所有指定标签的资源
            placeholders = ','.join(['?'] * len(filter_tags))
            query = f"""
            SELECT DISTINCT r.* FROM resources r
            JOIN tags t ON r.id = t.resource_id
            WHERE r.type = ? AND t.tag IN ({placeholders})
            GROUP BY r.id
            HAVING COUNT(DISTINCT t.tag) = ?
            """
            cursor.execute(query, (resource_type, *filter_tags, len(filter_tags)))
        else:
            cursor.execute(
                "SELECT * FROM resources WHERE type = ?",
                (resource_type,)
            )
        
        results = []
        for row in cursor.fetchall():
            # 获取标签
            cursor.execute(
                "SELECT tag FROM tags WHERE resource_id = ?",
                (row['id'],)
            )
            tags = [r['tag'] for r in cursor.fetchall()]
            
            extra = json.loads(row['extra']) if row['extra'] else {}
            
            results.append({
                "id": row['id'],
                "type": row['type'],
                "backend": row['backend'],
                "data_key": row['data_key'],
                "created_at": row['created_at'],
                "updated_at": row['updated_at'],
                "tags": tags,
                "extra": extra
            })
        
        return results