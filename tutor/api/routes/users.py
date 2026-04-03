"""User API Routes

提供用户管理端点：
- GET /api/v1/users/me - 获取当前用户
- PUT /api/v1/users/me - 更新当前用户
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

from tutor.core.auth import (
    hash_password,
    JWTManager,
    UserManager,
    TokenBlacklist,
    User,
    UserUpdate,
    get_token_blacklist,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# 依赖注入
_jwt_manager: Optional[JWTManager] = None
_user_manager: Optional[UserManager] = None


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


# ==================== Request/Response Models ====================


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None


async def get_current_user(
    authorization: Optional[str] = Header(None),
    jwt_mgr: JWTManager = Depends(get_jwt_manager),
    db: UserManager = Depends(get_db),
    blacklist: TokenBlacklist = Depends(get_token_blacklist),
) -> User:
    """获取当前认证用户

    从 Authorization header 解析 JWT token 并返回用户信息。
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "unauthorized", "message": "Missing authorization header"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 解析 Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "invalid_token", "message": "Invalid authorization header format"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        payload = jwt_mgr.decode_token(token)

        # 确保是 access token
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "invalid_token", "message": "Not an access token"}},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 检查是否已被撤销
        jti = payload.get("jti")
        if jti:
            is_revoked = await blacklist.is_token_revoked(jti)
            if is_revoked:
                raise HTTPException(
                    status_code=401,
                    detail={"error": {"code": "token_revoked", "message": "Token has been revoked"}},
                    headers={"WWW-Authenticate": "Bearer"},
                )

        user_id = payload.get("sub")
        user = db.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "user_not_found", "message": "User not found"}},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "account_disabled", "message": "Account has been disabled"}},
            )

        return user

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "invalid_token", "message": "Invalid or expired token"}},
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==================== Routes ====================


@router.get(
    "/me",
    response_model=dict,
    responses={
        200: {"description": "Current user profile"},
        401: {"description": "Not authenticated"},
    },
)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "data": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at,
            "updated_at": current_user.updated_at,
            "last_login_at": current_user.last_login_at,
        }
    }


@router.put(
    "/me",
    response_model=dict,
    responses={
        200: {"description": "User updated successfully"},
        401: {"description": "Not authenticated"},
        422: {"description": "Validation error"},
    },
)
async def update_me(
    request: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: UserManager = Depends(get_db),
):
    """更新当前用户信息"""
    # 验证更新数据
    try:
        update_data = UserUpdate(
            email=request.email,
            password=request.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 如果更新密码，先哈希
    password_hash = None
    if request.password:
        password_hash = hash_password(request.password)

    # 更新用户
    updated_user = db.update_user(
        current_user.id,
        update_data,
        password_hash=password_hash,
    )

    if not updated_user:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "user_not_found", "message": "User not found"}},
        )

    return {
        "data": {
            "id": updated_user.id,
            "username": updated_user.username,
            "email": updated_user.email,
            "role": updated_user.role,
            "updated_at": updated_user.updated_at,
        }
    }
