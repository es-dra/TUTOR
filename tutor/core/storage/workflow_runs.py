"""Workflow Runs 数据库存储

持久化存储工作流运行记录，支持：
- 运行状态查询
- 按状态/类型筛选
- 结果存储
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RunStorage:
    """工作流运行存储

    使用 SQLite 数据库持久化工作流运行记录。
    支持按状态、类型筛选和结果存储。
    使用每线程独立连接避免并发问题。
    """

    def __init__(self, db_path: str = "data/tutor_runs.db"):
        """初始化存储

        Args:
            db_path: 数据库路径
        """
        if isinstance(db_path, str) and db_path.startswith("sqlite:///"):
            db_path = db_path[len("sqlite:///") :]
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def _get_conn(self):
        """获取当前线程的数据库连接（每线程独立连接）"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            import sqlite3

            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            if not hasattr(self._local, "tables_initialized"):
                self._init_tables(conn)
                self._local.tables_initialized = True
            return conn
        return self._local.conn

    def _init_tables(self, conn) -> None:
        """初始化数据表"""
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_runs (
            run_id TEXT PRIMARY KEY,
            workflow_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            params TEXT,
            config TEXT,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            tags TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        self._migrate_missing_columns(cursor)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_status ON workflow_runs(status)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_type ON workflow_runs(workflow_type)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id)
        """)

        conn.commit()

    def _migrate_missing_columns(self, cursor) -> None:
        """迁移已存在的数据表，添加缺失的列"""
        try:
            cursor.execute("PRAGMA table_info(workflow_runs)")
            columns = [row[1] for row in cursor.fetchall()]
            if "tags" not in columns:
                cursor.execute(
                    "ALTER TABLE workflow_runs ADD COLUMN tags TEXT DEFAULT '[]'"
                )
        except Exception as e:
            logger.warning(f"Migration check failed: {e}")

    def close(self) -> None:
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
            logger.debug("RunStorage connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def create_run(
        self,
        run_id: str,
        workflow_type: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建新的工作流运行记录"""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat() + "Z"
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO workflow_runs
            (run_id, workflow_type, status, params, config, started_at, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                workflow_type,
                json.dumps(params, ensure_ascii=False) if params else None,
                json.dumps(config, ensure_ascii=False) if config else None,
                now,
                now,
                now,
            ),
        )

        conn.commit()

        logger.info(f"Created workflow run: {run_id} ({workflow_type})")

        return {
            "run_id": run_id,
            "workflow_type": workflow_type,
            "status": "pending",
            "params": params or {},
            "config": config or {},
            "started_at": now,
            "completed_at": None,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流运行记录"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_run(row)

    def _row_to_run(self, row) -> Dict[str, Any]:
        """将数据库行转换为运行字典"""
        return {
            "run_id": row["run_id"],
            "workflow_type": row["workflow_type"],
            "status": row["status"],
            "params": json.loads(row["params"]) if row["params"] else {},
            "config": json.loads(row["config"]) if row["config"] else {},
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "result": json.loads(row["result"]) if row["result"] else None,
            "error": row["error"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def update_status(
        self,
        run_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> bool:
        """更新工作流运行状态"""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat() + "Z"
        cursor = conn.cursor()

        if status in ["running", "completed", "failed", "cancelled"]:
            if result is not None and error is not None:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, completed_at = ?, result = ?, error = ?, updated_at = ? WHERE run_id = ?",
                    (
                        status,
                        now,
                        json.dumps(result, ensure_ascii=False),
                        error,
                        now,
                        run_id,
                    ),
                )
            elif result is not None:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, completed_at = ?, result = ?, updated_at = ? WHERE run_id = ?",
                    (
                        status,
                        now,
                        json.dumps(result, ensure_ascii=False),
                        now,
                        run_id,
                    ),
                )
            elif error is not None:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, completed_at = ?, error = ?, updated_at = ? WHERE run_id = ?",
                    (status, now, error, now, run_id),
                )
            else:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, completed_at = ?, updated_at = ? WHERE run_id = ?",
                    (status, now, now, run_id),
                )
        else:
            if result is not None and error is not None:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, result = ?, error = ?, updated_at = ? WHERE run_id = ?",
                    (
                        status,
                        json.dumps(result, ensure_ascii=False),
                        error,
                        now,
                        run_id,
                    ),
                )
            elif result is not None:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, result = ?, updated_at = ? WHERE run_id = ?",
                    (status, json.dumps(result, ensure_ascii=False), now, run_id),
                )
            elif error is not None:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, error = ?, updated_at = ? WHERE run_id = ?",
                    (status, error, now, run_id),
                )
            else:
                cursor.execute(
                    "UPDATE workflow_runs SET status = ?, updated_at = ? WHERE run_id = ?",
                    (status, now, run_id),
                )

        conn.commit()

        if cursor.rowcount == 0:
            logger.warning(f"Run not found for update: {run_id}")
            return False

        logger.info(f"Updated run status: {run_id} -> {status}")
        return True

    def list_runs(
        self,
        status: Optional[str] = None,
        workflow_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """列出工作流运行"""
        conn = self._get_conn()
        cursor = conn.cursor()

        conditions = []
        values = []

        if status:
            conditions.append("status = ?")
            values.append(status)

        if workflow_type:
            conditions.append("workflow_type = ?")
            values.append(workflow_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(
            f"SELECT COUNT(*) FROM workflow_runs WHERE {where_clause}", values
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT * FROM workflow_runs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*values, limit, offset),
        )

        rows = cursor.fetchall()

        return {
            "total": total,
            "runs": [self._row_to_run(row) for row in rows],
        }

    def delete_run(self, run_id: str) -> bool:
        """删除工作流运行记录"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workflow_runs WHERE run_id = ?", (run_id,))
        conn.commit()
        return cursor.rowcount > 0

    def update_tags(self, run_id: str, tags: List[str]) -> bool:
        """更新工作流标签（用于归档、收藏等）

        Args:
            run_id: 工作流 ID
            tags: 标签列表，如 ["archived", "favorite"]

        Returns:
            是否更新成功
        """
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat() + "Z"
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE workflow_runs
            SET tags = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (json.dumps(tags, ensure_ascii=False), now, run_id),
        )

        conn.commit()
        return cursor.rowcount > 0

    def list_runs_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """按标签筛选工作流

        Args:
            tags: 标签列表
            match_all: True 表示必须包含所有标签，False 表示包含任一标签
            limit: 返回数量限制
            offset: 偏移量
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        if match_all:
            cursor.execute(
                f"""
                SELECT * FROM workflow_runs
                WHERE {" AND ".join(["tags LIKE ?" for _ in tags])}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (*[f'%"{tag}"%' for tag in tags], limit, offset),
            )
        else:
            cursor.execute(
                f"""
                SELECT * FROM workflow_runs
                WHERE {" OR ".join(["tags LIKE ?" for _ in tags])}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (*[f'%"{tag}"%' for tag in tags], limit, offset),
            )

        rows = cursor.fetchall()
        return [self._row_to_run(row) for row in rows]

    def add_event(
        self,
        run_id: str,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加运行事件（用于历史记录）"""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat() + "Z"
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO run_events (run_id, event_type, event_data, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                event_type,
                json.dumps(event_data, ensure_ascii=False) if event_data else None,
                now,
            ),
        )

        conn.commit()

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        """获取运行事件历史"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM run_events
            WHERE run_id = ?
            ORDER BY created_at ASC
            """,
            (run_id,),
        )

        events = []
        for row in cursor.fetchall():
            events.append(
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "event_type": row["event_type"],
                    "event_data": json.loads(row["event_data"])
                    if row["event_data"]
                    else None,
                    "created_at": row["created_at"],
                }
            )

        return events

    def get_stats(self) -> Dict[str, Any]:
        """获取运行统计"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM workflow_runs")
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM workflow_runs
            GROUP BY status
        """)
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT workflow_type, COUNT(*) as count
            FROM workflow_runs
            GROUP BY workflow_type
        """)
        by_type = {row["workflow_type"]: row["count"] for row in cursor.fetchall()}

        return {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
        }
