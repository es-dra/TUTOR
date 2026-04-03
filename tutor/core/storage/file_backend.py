"""文件系统存储后端

使用文件系统存储实际数据：
- JSON文件用于结构化数据
- 二进制文件用于大文件
- 按resource_type组织目录结构
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import StorageBackend, StorageError, StorageMetadata

logger = logging.getLogger(__name__)


class FileBackend(StorageBackend):
    """文件系统存储后端
    
    目录结构：
    {base_path}/
    ├── {resource_type}/
    │   ├── {resource_id}.json        # 元数据
    │   ├── {resource_id}.data        # 实际数据
    │   └── attachments/              # 附件
    └── temp/                         # 临时文件
    """
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self._initialized = False
    
    def initialize(self) -> None:
        """初始化目录结构"""
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # 创建通用目录（测试期望这两个目录存在）
        (self.base_path / "data").mkdir(exist_ok=True)
        (self.base_path / "metadata").mkdir(exist_ok=True)
        (self.base_path / "temp").mkdir(exist_ok=True)
        
        self._initialized = True
        logger.info(f"File backend initialized: {self.base_path}")
    
    def _get_resource_dir(self, resource_type: str) -> Path:
        """获取资源类型目录"""
        return self.base_path / resource_type
    
    def _validate_resource_id(self, resource_type: str, resource_id: str) -> None:
        """检查路径遍历攻击：确保最终路径仍在 base_path 内"""
        res_dir = self._get_resource_dir(resource_type)
        candidate = (res_dir / resource_id).resolve()
        try:
            candidate.relative_to(self.base_path.resolve())
        except ValueError:
            raise StorageError(
                f"Invalid resource_id '{resource_id}': path traversal detected"
            )

    def _get_resource_paths(self, resource_type: str, resource_id: str) -> Dict[str, Path]:
        """获取资源相关路径"""
        self._validate_resource_id(resource_type, resource_id)
        res_dir = self._get_resource_dir(resource_type)
        res_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            "metadata": res_dir / f"{resource_id}.json",
            "data": res_dir / f"{resource_id}.data",
            "attachments": res_dir / f"{resource_id}_attachments"
        }
    
    def save(self,
             data: Any,
             resource_type: str,
             resource_id: str,
             metadata: Optional[StorageMetadata] = None) -> str:
        """保存数据和元数据
        
        Args:
            data: 实际数据（将序列化为JSON）
            resource_type: 资源类型
            resource_id: 资源ID
            metadata: 可选元数据
            
        Returns:
            resource_id
        """
        if not self._initialized:
            raise StorageError("Backend not initialized. Call initialize() first.")
        
        paths = self._get_resource_paths(resource_type, resource_id)
        
        now = datetime.now(timezone.utc).isoformat() + "Z"
        
        # 保存实际数据
        try:
            if isinstance(data, (dict, list)):
                with open(paths["data"], 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            elif isinstance(data, bytes):
                with open(paths["data"], 'wb') as f:
                    f.write(data)
            else:
                # 其他类型尝试转换
                with open(paths["data"], 'w', encoding='utf-8') as f:
                    f.write(str(data))
        except Exception as e:
            raise StorageError(f"Failed to save data: {e}")
        
        # 保存元数据
        if metadata:
            meta_dict = {
                "id": metadata.id,
                "type": metadata.type,
                "created_at": metadata.created_at or now,
                "updated_at": now,
                "tags": metadata.tags or [],
                "extra": metadata.extra or {}
            }
        else:
            meta_dict = {
                "id": resource_id,
                "type": resource_type,
                "created_at": now,
                "updated_at": now,
                "tags": [],
                "extra": {}
            }
        
        try:
            with open(paths["metadata"], 'w', encoding='utf-8') as f:
                json.dump(meta_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # 删除已保存的数据
            paths["data"].unlink(missing_ok=True)
            raise StorageError(f"Failed to save metadata: {e}")
        
        logger.debug(f"Saved resource: {resource_type}/{resource_id}")
        return resource_id
    
    def load(self,
             resource_type: str,
             resource_id: str,
             default: Any = None,
             return_metadata: bool = False) -> Optional[Any]:
        """加载数据
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            default: 默认值
            return_metadata: 若为 True，返回 (data, StorageMetadata) 元组
        """
        if not self._initialized:
            raise StorageError("Backend not initialized. Call initialize() first.")
        
        paths = self._get_resource_paths(resource_type, resource_id)
        
        # 检查数据文件是否存在
        if not paths["data"].exists():
            return (default, None) if return_metadata else default
        
        try:
            # 尝试作为JSON加载
            try:
                with open(paths["data"], 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                # 不是JSON，作为文本读取
                with open(paths["data"], 'r', encoding='utf-8') as f:
                    data = f.read()
            
            if not return_metadata:
                return data
            
            # 加载元数据
            meta = None
            if paths["metadata"].exists():
                try:
                    with open(paths["metadata"], 'r', encoding='utf-8') as f:
                        meta_dict = json.load(f)
                    meta = StorageMetadata(
                        id=meta_dict.get("id", resource_id),
                        type=meta_dict.get("type", resource_type),
                        created_at=meta_dict.get("created_at", ""),
                        updated_at=meta_dict.get("updated_at", ""),
                        tags=meta_dict.get("tags", []),
                        extra=meta_dict.get("extra", {})
                    )
                except Exception:
                    pass
            return data, meta
            
        except Exception as e:
            logger.error(f"Failed to load data {resource_id}: {e}")
            return (default, None) if return_metadata else default
    
    def delete(self, resource_type: str, resource_id: str) -> bool:
        """删除资源"""
        if not self._initialized:
            raise StorageError("Backend not initialized. Call initialize() first.")
        
        paths = self._get_resource_paths(resource_type, resource_id)
        
        deleted = False
        
        # 删除数据文件
        if paths["data"].exists():
            paths["data"].unlink()
            deleted = True
        
        # 删除元数据文件
        if paths["metadata"].exists():
            paths["metadata"].unlink()
            deleted = True
        
        # 删除附件目录
        if paths["attachments"].exists():
            import shutil
            try:
                shutil.rmtree(paths["attachments"])
                deleted = True
            except Exception as e:
                logger.warning(f"Failed to remove attachments: {e}")
        
        if deleted:
            logger.debug(f"Deleted resource: {resource_type}/{resource_id}")
        
        return deleted
    
    def exists(self, resource_type: str, resource_id: str) -> bool:
        """检查资源是否存在"""
        if not self._initialized:
            raise StorageError("Backend not initialized. Call initialize() first.")
        
        paths = self._get_resource_paths(resource_type, resource_id)
        return paths["data"].exists() or paths["metadata"].exists()
    
    def list(self,
             resource_type: str,
             filter_tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """列出资源
        
        注意：文件后端不存储标签元数据，标签查询需要配合SQLite后端。
        这里返回基本列表。
        """
        if not self._initialized:
            raise StorageError("Backend not initialized. Call initialize() first.")
        
        res_dir = self._get_resource_dir(resource_type)
        if not res_dir.exists():
            return []
        
        results = []
        
        # 查找所有.json元数据文件
        for meta_file in res_dir.glob("*.json"):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                # 如果有标签过滤，检查标签
                if filter_tags:
                    resource_tags = set(meta.get("tags", []))
                    if not all(tag in resource_tags for tag in filter_tags):
                        continue
                
                # 提取基本信息
                results.append({
                    "id": meta["id"],
                    "type": meta["type"],
                    "created_at": meta["created_at"],
                    "updated_at": meta["updated_at"],
                    "tags": meta.get("tags", []),
                    "extra": meta.get("extra", {})
                })
            except Exception as e:
                logger.warning(f"Failed to read metadata {meta_file}: {e}")
                continue
        
        return results
    
    def get_data_path(self, resource_type: str, resource_id: str) -> Optional[Path]:
        """获取数据文件路径（供外部使用）"""
        if not self._initialized:
            raise StorageError("Backend not initialized. Call initialize() first.")
        
        paths = self._get_resource_paths(resource_type, resource_id)
        return paths["data"] if paths["data"].exists() else None
    
    def close(self) -> None:
        """关闭（文件后端不需要特殊清理）"""
        self._initialized = False
        logger.debug("File backend closed")