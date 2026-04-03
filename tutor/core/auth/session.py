"""Session 管理与 Token 黑名单

提供 token 撤销（logout）功能。
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .jwt import JWTManager


class TokenBlacklist:
    """Token 黑名单管理器"""

    def __init__(self, db_path: str = "tutor.db"):
        """初始化 Token 黑名单管理器

        Args:
            db_path: 数据库路径
        """
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """确保 token_blacklist 表存在"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jti TEXT UNIQUE NOT NULL,
                token_type TEXT NOT NULL,
                user_id TEXT,
                revoked_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        # 创建索引加速查询
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_token_blacklist_jti ON token_blacklist(jti)
        """)

        conn.commit()
        conn.close()

    def _get_conn(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    async def revoke_token(
        self,
        jti: str,
        user_id: str,
        token_type: str,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        """撤销一个 token

        Args:
            jti: JWT ID
            user_id: 用户ID
            token_type: token类型 ("access" 或 "refresh")
            expires_at: token过期时间

        Returns:
            是否成功撤销
        """
        if expires_at is None:
            # 默认7天后过期
            expires_at = datetime.now(timezone.utc)

        conn = self._get_conn()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat() + "Z"
        expires_str = expires_at.isoformat() + "Z" if hasattr(expires_at, 'isoformat') else expires_at

        try:
            cursor.execute(
                """
                INSERT INTO token_blacklist (jti, token_type, user_id, revoked_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (jti, token_type, user_id, now, expires_str),
            )
            conn.commit()
            result = True
        except sqlite3.IntegrityError:
            # 已经撤销过
            result = True
        finally:
            conn.close()

        return result

    async def is_token_revoked(self, jti: str) -> bool:
        """检查 token 是否已被撤销

        Args:
            jti: JWT ID

        Returns:
            token是否已被撤销
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM token_blacklist WHERE jti = ? LIMIT 1",
            (jti,),
        )
        row = cursor.fetchone()
        conn.close()

        return row is not None

    def cleanup_expired_tokens(self) -> int:
        """清理已过期的黑名单记录

        Returns:
            删除的记录数
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat() + "Z"
        cursor.execute(
            "DELETE FROM token_blacklist WHERE expires_at < ?",
            (now,),
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted


# 全局单例
_token_blacklist: Optional[TokenBlacklist] = None


def get_token_blacklist(db_path: str = "tutor.db") -> TokenBlacklist:
    """获取 TokenBlacklist 单例

    Args:
        db_path: 数据库路径

    Returns:
        TokenBlacklist实例
    """
    global _token_blacklist
    if _token_blacklist is None:
        _token_blacklist = TokenBlacklist(db_path)
    return _token_blacklist
