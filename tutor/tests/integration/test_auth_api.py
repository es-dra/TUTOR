"""User Authentication API Integration Tests

测试完整的认证流程：
- 用户注册 POST /api/v1/auth/register
- 用户登录 POST /api/v1/auth/login
- 用户登出 POST /api/v1/auth/logout
- 令牌刷新 POST /api/v1/auth/refresh
- 获取当前用户 GET /api/v1/users/me
- 更新用户 PUT /api/v1/users/me
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["TUTOR_DB_PATH"] = path
    yield path
    try:
        os.unlink(path)
    except:
        pass
    if "TUTOR_DB_PATH" in os.environ:
        del os.environ["TUTOR_DB_PATH"]


@pytest.fixture
def client(temp_db):
    """创建测试客户端"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from tutor.api.main import create_app

    # Reset global singletons
    import tutor.api.routes.auth as auth_module
    import tutor.api.routes.users as users_module
    auth_module._jwt_manager = None
    auth_module._user_manager = None
    auth_module._token_blacklist = None
    auth_module._rate_limiter = None
    auth_module._password_validator = None
    users_module._jwt_manager = None
    users_module._user_manager = None

    app = create_app()
    yield TestClient(app)

    # Cleanup singletons
    auth_module._jwt_manager = None
    auth_module._user_manager = None
    auth_module._token_blacklist = None
    auth_module._rate_limiter = None
    auth_module._password_validator = None
    users_module._jwt_manager = None
    users_module._user_manager = None


class TestAuthRegister:
    """用户注册测试"""

    def test_register_success(self, client):
        """有效数据应该注册成功"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "SecurePass123!"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "data" in data
        assert data["data"]["username"] == "newuser"
        assert data["data"]["email"] == "newuser@example.com"
        assert data["data"]["role"] == "user"
        assert "id" in data["data"]
        assert "password" not in data["data"]
        assert "password_hash" not in data["data"]

    def test_register_duplicate_username(self, client):
        """重复用户名应该返回409"""
        # 先注册一个用户
        response1 = client.post(
            "/api/v1/auth/register",
            json={
                "username": "duplicateuser",
                "email": "user1@example.com",
                "password": "SecurePass123!"
            }
        )
        assert response1.status_code == 201

        # 尝试用相同用户名注册
        response2 = client.post(
            "/api/v1/auth/register",
            json={
                "username": "duplicateuser",
                "email": "user2@example.com",
                "password": "SecurePass123!"
            }
        )

        assert response2.status_code == 409
        data = response2.json()
        assert "error" in data or "detail" in data

    def test_register_duplicate_email(self, client):
        """重复邮箱应该返回409"""
        # 先注册一个用户
        response1 = client.post(
            "/api/v1/auth/register",
            json={
                "username": "user1",
                "email": "sameemail@example.com",
                "password": "SecurePass123!"
            }
        )
        assert response1.status_code == 201

        # 尝试用相同邮箱注册
        response2 = client.post(
            "/api/v1/auth/register",
            json={
                "username": "user2",
                "email": "sameemail@example.com",
                "password": "SecurePass123!"
            }
        )

        assert response2.status_code == 409

    def test_register_invalid_email(self, client):
        """无效邮箱格式应该返回422"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "not-an-email",
                "password": "SecurePass123!"
            }
        )

        assert response.status_code == 422

    def test_register_short_password(self, client):
        """密码太短应该返回422"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "short"
            }
        )

        assert response.status_code == 422


class TestAuthLogin:
    """用户登录测试"""

    def test_login_success(self, client):
        """有效凭据应该登录成功并返回token"""
        # 先注册
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "loginuser",
                "email": "login@example.com",
                "password": "SecurePass123!"
            }
        )

        # 登录
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "loginuser",
                "password": "SecurePass123!"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert "expires_in" in data["data"]

    def test_login_wrong_password(self, client):
        """错误密码应该返回401"""
        # 先注册
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "loginuser2",
                "email": "login2@example.com",
                "password": "SecurePass123!"
            }
        )

        # 错误密码登录
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "loginuser2",
                "password": "WrongPassword456!"
            }
        )

        assert response.status_code == 401

    def test_login_nonexistent_user(self, client):
        """不存在的用户应该返回401"""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "nonexistent",
                "password": "SomePassword123!"
            }
        )

        assert response.status_code == 401


class TestAuthLogout:
    """用户登出测试"""

    def test_logout_success(self, client):
        """有效token应该能成功登出"""
        # 注册并登录
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "logoutuser",
                "email": "logout@example.com",
                "password": "SecurePass123!"
            }
        )

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "logoutuser",
                "password": "SecurePass123!"
            }
        )

        token = login_response.json()["data"]["access_token"]

        # 登出
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_logout_no_token(self, client):
        """没有token应该返回401"""
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 401


class TestAuthRefresh:
    """令牌刷新测试"""

    def test_refresh_success(self, client):
        """有效refresh token应该能获取新access token"""
        # 注册并登录
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "refreshuser",
                "email": "refresh@example.com",
                "password": "SecurePass123!"
            }
        )

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "refreshuser",
                "password": "SecurePass123!"
            }
        )

        refresh_token = login_response.json()["data"]["refresh_token"]

        # 刷新
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "access_token" in data["data"]

    def test_refresh_invalid_token(self, client):
        """无效refresh token应该返回401"""
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"}
        )

        assert response.status_code == 401


class TestUserMe:
    """当前用户信息测试"""

    def test_get_me_success(self, client):
        """有效token应该能获取当前用户信息"""
        # 注册并登录
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "meuser",
                "email": "me@example.com",
                "password": "SecurePass123!"
            }
        )

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "meuser",
                "password": "SecurePass123!"
            }
        )

        token = login_response.json()["data"]["access_token"]

        # 获取当前用户
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["username"] == "meuser"
        assert data["data"]["email"] == "me@example.com"

    def test_get_me_no_token(self, client):
        """没有token应该返回401"""
        response = client.get("/api/v1/users/me")
        assert response.status_code == 401


class TestUserUpdate:
    """用户更新测试"""

    def test_update_email_success(self, client):
        """应该能更新邮箱"""
        # 注册并登录
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "updateuser",
                "email": "old@example.com",
                "password": "SecurePass123!"
            }
        )

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "updateuser",
                "password": "SecurePass123!"
            }
        )

        token = login_response.json()["data"]["access_token"]

        # 更新邮箱
        response = client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["email"] == "new@example.com"

    def test_update_password_success(self, client):
        """应该能更新密码"""
        # 注册并登录
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "pwuser",
                "email": "pw@example.com",
                "password": "SecurePass123!"
            }
        )

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "pwuser",
                "password": "SecurePass123!"
            }
        )

        token = login_response.json()["data"]["access_token"]

        # 更新密码
        response = client.put(
            "/api/v1/users/me",
            json={"password": "NewSecurePass123!"},
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_update_no_token(self, client):
        """没有token应该返回401"""
        response = client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"}
        )
        assert response.status_code == 401
