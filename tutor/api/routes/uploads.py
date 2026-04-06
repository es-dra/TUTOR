"""File Upload API Routes

提供文件上传端点，用于上传本地文献文件。
"""

import os
import uuid
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])

# 上传文件存储目录
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 最大文件大小: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


class UploadResponse(BaseModel):
    """上传响应"""

    file_id: str
    filename: str
    path: str
    size: int


class UploadListResponse(BaseModel):
    """文件列表响应"""

    files: List[UploadResponse]


@router.post("")
async def upload_file(file: UploadFile = File(...)):
    """上传单个文件

    Args:
        file: 上传的文件

    Returns:
        上传的文件信息，包含服务器端路径
    """
    from tutor.api.models import success_response
    
    # 验证文件类型
    allowed_extensions = {".pdf", ".txt", ".md", ".tex", ".docx"}
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported: {', '.join(allowed_extensions)}",
        )

    # 生成唯一文件名避免冲突
    file_id = str(uuid.uuid4())[:8]
    safe_filename = f"{file_id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename

    # 保存文件
    try:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Uploaded file: {file.filename} -> {file_path}")

        return success_response(data=UploadResponse(
            file_id=file_id,
            filename=file.filename,
            path=str(file_path),
            size=len(content),
        ))

    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")


@router.post("/multiple")
async def upload_multiple_files(files: List[UploadFile] = File(...)):
    """上传多个文件

    Args:
        files: 上传的文件列表

    Returns:
        上传的文件信息列表
    """
    from tutor.api.models import success_response
    
    results = []

    for file in files:
        try:
            # 验证文件类型
            file_ext = Path(file.filename).suffix.lower()
            allowed_extensions = {".pdf", ".txt", ".md", ".tex", ".docx"}

            if file_ext not in allowed_extensions:
                logger.warning(f"Skipping unsupported file: {file.filename}")
                continue

            # 生成唯一文件名
            file_id = str(uuid.uuid4())[:8]
            safe_filename = f"{file_id}_{file.filename}"
            file_path = UPLOAD_DIR / safe_filename

            # 保存文件
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                logger.warning(f"Skipping oversized file: {file.filename}")
                continue
            with open(file_path, "wb") as f:
                f.write(content)

            results.append(
                UploadResponse(
                    file_id=file_id,
                    filename=file.filename,
                    path=str(file_path),
                    size=len(content),
                )
            )

            logger.info(f"Uploaded file: {file.filename} -> {file_path}")

        except Exception as e:
            logger.error(f"Failed to save uploaded file {file.filename}: {e}")
            continue

    return success_response(data=results)


@router.get("")
async def list_uploaded_files():
    """列出已上传的文件"""
    from tutor.api.models import success_response
    
    files = []

    try:
        for file_path in UPLOAD_DIR.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                # 从文件名提取原始名称 (格式: uuid_originalname)
                parts = file_path.name.split("_", 1)
                original_name = parts[1] if len(parts) > 1 else file_path.name

                files.append(
                    UploadResponse(
                        file_id=parts[0] if len(parts) > 1 else "unknown",
                        filename=original_name,
                        path=str(file_path),
                        size=stat.st_size,
                    )
                )
    except Exception as e:
        logger.error(f"Failed to list uploaded files: {e}")

    return success_response(data=UploadListResponse(files=files))


@router.delete("/{file_id}")
async def delete_uploaded_file(file_id: str):
    """删除已上传的文件

    Args:
        file_id: 文件 ID
    """
    from tutor.api.models import success_response
    
    try:
        for file_path in UPLOAD_DIR.iterdir():
            if file_path.is_file() and file_path.name.startswith(file_id):
                file_path.unlink()
                logger.info(f"Deleted file: {file_path}")
                return success_response(data={"status": "deleted", "file_id": file_id})

        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")
