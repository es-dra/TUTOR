"""User Authentication 单元测试

测试用户认证核心功能：
- 密码哈希与验证
- JWT令牌创建与验证
- 用户模型操作
- Token黑名单管理
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import uuid


class TestPasswordHashing:
    """密码哈希测试"""

    def test_hash_password_creates_hash(self):
        """密码应该被哈希化，不能被还原"""
        pytest.importorskip("passlib")
        from tutor.core.auth.password import hash_password

        password = "SecurePass123!"
        hashed = hash_password(password)

        # 哈希后的密码不应等于原密码
        assert hashed != password
        # 哈希应该以算法标识开头
        assert hashed.startswith("$argon2") or hashed.startswith("$2b$")

    def test_verify_password_correct(self):
        """正确的密码应该通过验证"""
        pytest.importorskip("passlib")
        from tutor.core.auth.password import hash_password, verify_password

        password = "SecurePass123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """错误的密码不应该通过验证"""
        pytest.importorskip("passlib")
        from tutor.core.auth.password import hash_password, verify_password

        password = "SecurePass123!"
        wrong_password = "WrongPassword456!"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_same_password_different_hashes(self):
        """同一密码每次哈希应该不同（salt）"""
        pytest.importorskip("passlib")
        from tutor.core.auth.password import hash_password

        password = "SecurePass123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # 哈希应该不同（不同的salt）
        assert hash1 != hash2
        # 但两个哈希都应该能验证原密码
        from tutor.core.auth.password import verify_password
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    """JWT令牌测试"""

    @pytest.fixture
    def jwt_module(self):
        pytest.importorskip("jose")
        from tutor.core.auth.jwt import JWTManager
        # 使用测试密钥
        with patch.dict("os.environ", {"AUTH_SECRET_KEY": "test-secret-key-for-testing-only"}):
            yield JWTManager()

    def test_create_access_token(self, jwt_module):
        """应该创建有效的access token"""
        user_id = "usr_test123"
        token = jwt_module.create_access_token(user_id)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT格式：header.payload.signature
        parts = token.split(".")
        assert len(parts) == 3

    def test_decode_access_token(self, jwt_module):
        """应该能解码有效的access token"""
        user_id = "usr_test123"
        token = jwt_module.create_access_token(user_id)

        payload = jwt_module.decode_token(token)

        assert payload is not None
        assert payload.get("sub") == user_id
        assert payload.get("type") == "access"

    def test_create_refresh_token(self, jwt_module):
        """应该创建有效的refresh token"""
        user_id = "usr_test123"
        token = jwt_module.create_refresh_token(user_id)

        assert token is not None
        assert isinstance(token, str)

        payload = jwt_module.decode_token(token)
        assert payload.get("sub") == user_id
        assert payload.get("type") == "refresh"

    def test_access_token_expires(self, jwt_module):
        """access token应该有 expiration"""
        user_id = "usr_test123"
        token = jwt_module.create_access_token(user_id)

        payload = jwt_module.decode_token(token)

        assert "exp" in payload
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        # access token 默认30分钟过期
        assert exp_time > now + timedelta(minutes=25)
        assert exp_time < now + timedelta(minutes=35)

    def test_refresh_token_longer_expiration(self, jwt_module):
        """refresh token应该有更长的 expiration"""
        user_id = "usr_test123"
        token = jwt_module.create_refresh_token(user_id)

        payload = jwt_module.decode_token(token)

        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        # refresh token 默认7天过期
        assert exp_time > now + timedelta(days=6)
        assert exp_time < now + timedelta(days=8)

    def test_decode_invalid_token(self, jwt_module):
        """无效的token应该抛出异常"""
        from jose.exceptions import JWTError

        with pytest.raises(JWTError):
            jwt_module.decode_token("invalid.token.here")

    def test_token_contains_jti(self, jwt_module):
        """token应该包含jti（JWT ID）用于撤销"""
        user_id = "usr_test123"
        token = jwt_module.create_access_token(user_id)

        payload = jwt_module.decode_token(token)

        assert "jti" in payload
        assert payload["jti"] is not None


class TestUserModel:
    """用户模型测试"""

    def test_user_dataclass_creation(self):
        """应该能创建User dataclass"""
        pytest.importorskip("pydantic")
        from tutor.core.auth.user import User

        user = User(
            id="usr_test123",
            username="testuser",
            email="test@example.com",
            password_hash="$argon2$hash",
            role="user",
            is_active=True,
        )

        assert user.id == "usr_test123"
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.password_hash == "$argon2$hash"
        assert user.role == "user"
        assert user.is_active is True

    def test_user_create_validation(self):
        """UserCreate应该有验证"""
        pytest.importorskip("pydantic")
        from tutor.core.auth.user import UserCreate

        # 有效数据
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecurePass123!",
        )
        assert user_data.username == "testuser"

        # 无效邮箱应该失败
        with pytest.raises(ValueError):
            UserCreate(
                username="testuser",
                email="invalid-email",
                password="SecurePass123!",
            )

    def test_user_create_password_min_length(self):
        """密码最短长度验证"""
        pytest.importorskip("pydantic")
        from tutor.core.auth.user import UserCreate

        # 密码太短应该失败
        with pytest.raises(ValueError):
            UserCreate(
                username="testuser",
                email="test@example.com",
                password="short",  # 少于8字符
            )


class TestTokenBlacklist:
    """Token黑名单测试"""

    @pytest.fixture
    def blacklist(self):
        pytest.importorskip("jose")
        from tutor.core.auth.session import TokenBlacklist
        # 使用临时数据库
        import tempfile
        import os
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield TokenBlacklist(db_path=db_path)
        # 清理
        try:
            os.unlink(db_path)
        except:
            pass

    @pytest.mark.asyncio
    async def test_revoke_token(self, blacklist):
        """撤销的token应该被记录"""
        jti = str(uuid.uuid4())
        user_id = "usr_test123"

        result = await blacklist.revoke_token(jti, user_id, "access")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_token_revoked_true(self, blacklist):
        """已撤销的token应该返回True"""
        jti = str(uuid.uuid4())
        user_id = "usr_test123"

        await blacklist.revoke_token(jti, user_id, "access")
        is_revoked = await blacklist.is_token_revoked(jti)

        assert is_revoked is True

    @pytest.mark.asyncio
    async def test_is_token_revoked_false(self, blacklist):
        """未撤销的token应该返回False"""
        jti = str(uuid.uuid4())

        is_revoked = await blacklist.is_token_revoked(jti)

        assert is_revoked is False
