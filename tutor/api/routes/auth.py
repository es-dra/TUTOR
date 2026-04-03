"""Authentication API Routes

提供用户认证端点：
- POST /api/v1/auth/register - 用户注册
- POST /api/v1/auth/login - 用户登录
- POST /api/v1/auth/logout - 用户登出
- POST /api/v1/auth/refresh - 刷新令牌
"""

from datetime import datetime, timezone
from typing import Optional
import os

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

from tutor.core.auth import (
    hash_password,
    verify_password,
    JWTManager,
    UserManager,
    TokenBlacklist,
    UserCreate,
    UserLogin,
)
from tutor.core.auth.security import LoginRateLimiter, PasswordStrengthValidator

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 依赖注入
_jwt_manager: Optional[JWTManager] = None
_user_manager: Optional[UserManager] = None
_token_blacklist: Optional[TokenBlacklist] = None
_rate_limiter: Optional[LoginRateLimiter] = None
_password_validator: Optional[PasswordStrengthValidator] = None


def get_jwt_manager() -> JWTManager:
    global _jwt_manager
    if _jwt_manager is None:
        _jwt_manager = JWTManager()
    return _jwt_manager


def get_db() -> UserManager:
    global _user_manager
    if _user_manager is None:
        db_path = os.environ.get("TUTOR_DB_PATH", "tutor.db")
        _user_manager = UserManager(db_path)
    return _user_manager


def get_blacklist() -> TokenBlacklist:
    global _token_blacklist
    if _token_blacklist is None:
        db_path = os.environ.get("TUTOR_DB_PATH", "tutor.db")
        _token_blacklist = TokenBlacklist(db_path)
    return _token_blacklist


def get_rate_limiter() -> LoginRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        db_path = os.environ.get("TUTOR_DB_PATH", "tutor.db")
        _rate_limiter = LoginRateLimiter(
            db_path=db_path,
            max_attempts=5,
            lockout_duration=300,  # 5 minutes
        )
    return _rate_limiter


def get_password_validator() -> PasswordStrengthValidator:
    global _password_validator
    if _password_validator is None:
        _password_validator = PasswordStrengthValidator(
            min_length=8,
            require_uppercase=True,
            require_lowercase=True,
            require_number=True,
            require_special=True,
        )
    return _password_validator


# ==================== Request/Response Models ====================


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str
    code: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(code: str, message: str, field: Optional[str] = None, status_code: int = 400):
    """创建错误响应"""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": [{"field": field, "message": message, "code": code}] if field else []
        }
    }


# ==================== Routes ====================


@router.post(
    "/register",
    response_model=dict,
    status_code=201,
    responses={
        201: {"description": "User created successfully"},
        409: {"description": "Username or email already exists"},
        422: {"description": "Validation error"},
    },
)
async def register(
    request: RegisterRequest,
    db: UserManager = Depends(get_db),
    password_validator: PasswordStrengthValidator = Depends(get_password_validator),
):
    """用户注册"""
    # 验证密码强度
    if not password_validator.validate(request.password):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "weak_password",
                    "message": "Password does not meet strength requirements. Must be at least 8 characters with uppercase, lowercase, number, and special character.",
                }
            },
        )

    try:
        user_data = UserCreate(
            username=request.username,
            email=request.email,
            password=request.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 检查用户名是否已存在
    existing = db.get_user_by_username(request.username)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "username_taken", "message": "Username already exists"}},
        )

    # 检查邮箱是否已存在
    existing_email = db.get_user_by_email(request.email)
    if existing_email:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "email_taken", "message": "Email already exists"}},
        )

    # 创建用户
    password_hash = hash_password(request.password)
    user = db.create_user(user_data, password_hash)

    return {
        "data": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at,
        }
    }


@router.post(
    "/login",
    response_model=dict,
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"},
        403: {"description": "Account disabled"},
    },
)
async def login(
    request: LoginRequest,
    db: UserManager = Depends(get_db),
    jwt_mgr: JWTManager = Depends(get_jwt_manager),
    rate_limiter: LoginRateLimiter = Depends(get_rate_limiter),
):
    """用户登录"""
    # 检查账户是否被锁定
    if rate_limiter.is_locked(request.username):
        is_locked, remaining = rate_limiter.is_locked_with_remaining(request.username)
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "account_locked",
                    "message": f"Account is temporarily locked due to too many failed attempts. Try again in {remaining} seconds.",
                }
            },
        )

    # 获取用户
    user = db.get_user_by_username(request.username)

    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "invalid_credentials", "message": "Invalid username or password"}},
        )

    # 验证密码
    if not verify_password(request.password, user.password_hash):
        # 记录失败尝试
        rate_limiter.record_failed_attempt(request.username)
        remaining = rate_limiter.get_remaining_attempts(request.username)
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "invalid_credentials",
                    "message": f"Invalid username or password. {remaining} attempts remaining."
                    if remaining > 0
                    else "Invalid username or password. Account will be locked after next failed attempt.",
                }
            },
        )

    # 检查账户是否启用
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "account_disabled", "message": "Account has been disabled"}},
        )

    # 更新最后登录时间
    db.update_last_login(user.id)

    # 清除失败尝试记录
    rate_limiter.record_successful_login(request.username)

    # 创建token
    access_token = jwt_mgr.create_access_token(user.id)
    refresh_token = jwt_mgr.create_refresh_token(user.id)

    return {
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 1800,  # 30 minutes
        }
    }


@router.post(
    "/logout",
    response_model=dict,
    responses={
        200: {"description": "Logout successful"},
        401: {"description": "Invalid token"},
    },
)
async def logout(
    authorization: Optional[str] = Header(None),
    jwt_mgr: JWTManager = Depends(get_jwt_manager),
    blacklist: TokenBlacklist = Depends(get_blacklist),
):
    """用户登出"""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "unauthorized", "message": "Missing authorization header"}},
        )

    # 解析 Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "invalid_token", "message": "Invalid authorization header format"}},
        )

    token = parts[1]

    try:
        payload = jwt_mgr.decode_token(token)
        jti = payload.get("jti")
        user_id = payload.get("sub")
        token_type = payload.get("type", "access")

        if jti:
            await blacklist.revoke_token(jti, user_id, token_type)

        return {"data": {"message": "Successfully logged out"}}

    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "invalid_token", "message": "Invalid or expired token"}},
        )


@router.post(
    "/refresh",
    response_model=dict,
    responses={
        200: {"description": "Token refreshed successfully"},
        401: {"description": "Invalid refresh token"},
    },
)
async def refresh_token(
    request: RefreshRequest,
    jwt_mgr: JWTManager = Depends(get_jwt_manager),
    blacklist: TokenBlacklist = Depends(get_blacklist),
):
    """刷新访问令牌"""
    try:
        payload = jwt_mgr.decode_token(request.refresh_token)

        # 确保是 refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "invalid_token", "message": "Not a refresh token"}},
            )

        # 检查是否已被撤销
        jti = payload.get("jti")
        if jti:
            is_revoked = await blacklist.is_token_revoked(jti)
            if is_revoked:
                raise HTTPException(
                    status_code=401,
                    detail={"error": {"code": "token_revoked", "message": "Token has been revoked"}},
                )

        user_id = payload.get("sub")

        # 撤销旧的 refresh token
        if jti:
            await blacklist.revoke_token(jti, user_id, "refresh")

        # 创建新的 access token
        access_token = jwt_mgr.create_access_token(user_id)

        return {
            "data": {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": 1800,
            }
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "invalid_token", "message": "Invalid or expired refresh token"}},
        )
