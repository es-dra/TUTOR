"""TUTOR Cost Tracker - API 调用成本追踪

记录和查询模型调用成本，持久化到 SQLite。
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class CostEntry:
    """成本条目"""
    timestamp: str
    amount_usd: float
    model: str
    description: str
    workflow_id: str


class CostTracker:
    """成本追踪器"""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".tutor" / "costs.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cost_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                model TEXT NOT NULL,
                description TEXT,
                workflow_id TEXT
            )
        """)
        conn.commit()

    def record(self, entry: CostEntry) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO cost_entries (timestamp, amount_usd, model, description, workflow_id) VALUES (?, ?, ?, ?, ?)",
            (entry.timestamp, entry.amount_usd, entry.model, entry.description, entry.workflow_id),
        )
        conn.commit()

    def total(self) -> float:
        conn = self._get_conn()
        row = conn.execute("SELECT COALESCE(SUM(amount_usd), 0) as t FROM cost_entries").fetchone()
        return row["t"]

    def total_by_workflow(self, workflow_id: str) -> float:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) as t FROM cost_entries WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return row["t"]

    def total_by_model(self, model: str) -> float:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) as t FROM cost_entries WHERE model = ?",
            (model,),
        ).fetchone()
        return row["t"]

    def get_entries(self, since: Optional[str] = None, until: Optional[str] = None) -> List[CostEntry]:
        conn = self._get_conn()
        query = "SELECT timestamp, amount_usd, model, description, workflow_id FROM cost_entries WHERE 1=1"
        params: list = []
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        if until:
            query += " AND timestamp <= ?"
            params.append(until)
        query += " ORDER BY timestamp"
        rows = conn.execute(query, params).fetchall()
        return [CostEntry(**dict(r)) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
