"""JWT Token 管理模块

提供 JWT 令牌的创建、验证和刷新功能。
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from jose import jwt, JWTError
from pydantic import BaseModel


class TokenPayload(BaseModel):
    """Token载荷"""

    sub: str  # user_id
    type: str  # "access" or "refresh"
    jti: str  # JWT ID for revocation
    exp: datetime


class JWTManager:
    """JWT Token 管理器"""

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
    ):
        """初始化 JWT 管理器

        Args:
            secret_key: JWT签名密钥，默认从环境变量 AUTH_SECRET_KEY 读取
            algorithm: JWT算法，默认HS256
            access_token_expire_minutes: access token过期时间（分钟）
            refresh_token_expire_days: refresh token过期时间（天）
        """
        self.secret_key = secret_key or os.environ.get("AUTH_SECRET_KEY", "")
        if not self.secret_key:
            raise RuntimeError(
                "AUTH_SECRET_KEY environment variable is not set. "
                "In production, you MUST set a secure secret key. "
                "For development, set AUTH_SECRET_KEY=dev-secret-123"
            )
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    def create_access_token(self, user_id: str) -> str:
        """创建 access token

        Args:
            user_id: 用户ID

        Returns:
            JWT token字符串
        """
        return self._create_token(user_id, "access", self.access_token_expire_minutes)

    def create_refresh_token(self, user_id: str) -> str:
        """创建 refresh token

        Args:
            user_id: 用户ID

        Returns:
            JWT token字符串
        """
        return self._create_token(
            user_id, "refresh", self.refresh_token_expire_days * 24 * 60
        )

    def _create_token(self, user_id: str, token_type: str, expire_minutes: int) -> str:
        """创建JWT token

        Args:
            user_id: 用户ID
            token_type: token类型 ("access" 或 "refresh")
            expire_minutes: 过期时间（分钟）

        Returns:
            JWT token字符串
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=expire_minutes)
        jti = str(uuid.uuid4())  # Unique ID for revocation

        payload = {
            "sub": user_id,
            "type": token_type,
            "jti": jti,
            "exp": expire,
            "iat": now,
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Dict[str, Any]:
        """解码JWT token

        Args:
            token: JWT token字符串

        Returns:
            token载荷字典

        Raises:
            JWTError: token无效或已过期
        """
        return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

    def get_token_expiration(self, token: str) -> Optional[datetime]:
        """获取token的过期时间

        Args:
            token: JWT token字符串

        Returns:
            过期时间datetime对象
        """
        try:
            payload = self.decode_token(token)
            return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        except JWTError:
            return None

    def get_jti(self, token: str) -> Optional[str]:
        """获取token的JTI

        Args:
            token: JWT token字符串

        Returns:
            JTI字符串
        """
        try:
            payload = self.decode_token(token)
            return payload.get("jti")
        except JWTError:
            return None
