"""User 模型和数据库操作

提供用户数据模型和CRUD操作。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, field_validator


class User(BaseModel):
    """用户模型"""
    id: str
    username: str
    email: str
    password_hash: str
    role: str = "user"
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must be alphanumeric (underscores and hyphens allowed)")
        return v


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str
    password: str


class UserUpdate(BaseModel):
    """用户更新请求"""
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)


class UserInDB(User):
    """数据库中的用户模型（包含所有字段）"""
    pass


class UserManager:
    """用户管理CRUD操作"""

    def __init__(self, db_path: str = "tutor.db"):
        """初始化用户管理器

        Args:
            db_path: 数据库路径
        """
        import sqlite3
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """确保users表存在"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _get_conn(self):
        """获取数据库连接"""
        import sqlite3
        return sqlite3.connect(self.db_path)

    def create_user(self, user_data: UserCreate, password_hash: str) -> User:
        """创建新用户

        Args:
            user_data: 用户注册数据
            password_hash: 哈希后的密码

        Returns:
            创建的用户对象
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat() + "Z"
        user_id = f"usr_{uuid.uuid4().hex[:12]}"

        try:
            cursor.execute(
                """
                INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'user', 1, ?, ?)
                """,
                (user_id, user_data.username, user_data.email, password_hash, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.close()
            if "username" in str(e):
                raise ValueError("username_taken")
            elif "email" in str(e):
                raise ValueError("email_taken")
            raise
        finally:
            conn.close()

        return User(
            id=user_id,
            username=user_data.username,
            email=user_data.email,
            password_hash=password_hash,
            role="user",
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户

        Args:
            username: 用户名

        Returns:
            用户对象或None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, username, email, password_hash, role, is_active, created_at, updated_at, last_login_at FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0],
            username=row[1],
            email=row[2],
            password_hash=row[3],
            role=row[4],
            is_active=bool(row[5]),
            created_at=row[6],
            updated_at=row[7],
            last_login_at=row[8],
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户

        Args:
            email: 邮箱地址

        Returns:
            用户对象或None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, username, email, password_hash, role, is_active, created_at, updated_at, last_login_at FROM users WHERE email = ?",
            (email,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0],
            username=row[1],
            email=row[2],
            password_hash=row[3],
            role=row[4],
            is_active=bool(row[5]),
            created_at=row[6],
            updated_at=row[7],
            last_login_at=row[8],
        )

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据ID获取用户

        Args:
            user_id: 用户ID

        Returns:
            用户对象或None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, username, email, password_hash, role, is_active, created_at, updated_at, last_login_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return User(
            id=row[0],
            username=row[1],
            email=row[2],
            password_hash=row[3],
            role=row[4],
            is_active=bool(row[5]),
            created_at=row[6],
            updated_at=row[7],
            last_login_at=row[8],
        )

    def update_user(self, user_id: str, update_data: UserUpdate, password_hash: Optional[str] = None) -> Optional[User]:
        """更新用户信息

        Args:
            user_id: 用户ID
            update_data: 更新数据
            password_hash: 新密码哈希（如果更新密码）

        Returns:
            更新后的用户对象或None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat() + "Z"

        # 构建更新语句
        updates = []
        params = []

        if update_data.email:
            updates.append("email = ?")
            params.append(update_data.email)

        if password_hash:
            updates.append("password_hash = ?")
            params.append(password_hash)

        updates.append("updated_at = ?")
        params.append(now)

        if not updates:
            return self.get_user_by_id(user_id)

        params.append(user_id)

        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()

        return self.get_user_by_id(user_id)

    def update_last_login(self, user_id: str) -> None:
        """更新最后登录时间

        Args:
            user_id: 用户ID
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat() + "Z"
        cursor.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
        conn.commit()
        conn.close()

    def delete_user(self, user_id: str) -> bool:
        """删除用户

        Args:
            user_id: 用户ID

        Returns:
            是否成功删除
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def list_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """列出用户

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            用户列表
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, username, email, password_hash, role, is_active, created_at, updated_at, last_login_at FROM users LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        return [
            User(
                id=row[0],
                username=row[1],
                email=row[2],
                password_hash=row[3],
                role=row[4],
                is_active=bool(row[5]),
                created_at=row[6],
                updated_at=row[7],
                last_login_at=row[8],
            )
            for row in rows
        ]
