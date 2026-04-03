"""Checkpoint Validation - 检查点数据验证

提供检查点数据的 Sche 验证和自动修复功能。
"""

import json
import logging
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List

import jsonschema

logger = logging.getLogger(__name__)

# 检查点 JSON Schema（用于验证）
CHECKPOINT_SCHEMA = {
    "type": "object",
    "required": [
        "workflow_id",
        "workflow_type",
        "status",
        "current_step",
        "total_steps",
        "step_name",
        "input_data",
        "output_data",
        "created_at",
        "updated_at",
    ],
    "properties": {
        "workflow_id": {"type": "string"},
        "workflow_type": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["pending", "running", "completed", "failed", "cancelled"],
        },
        "current_step": {"type": "integer", "minimum": 0},
        "total_steps": {"type": "integer", "minimum": 1},
        "step_name": {"type": "string"},
        "input_data": {"type": "object"},
        "output_data": {"type": "object"},
        "error": {"type": ["string", "null"]},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
        "_crc32": {"type": "integer"},  # 可选，用于完整性校验
    },
    "additionalProperties": True,
}


class CheckpointValidator:
    """检查点验证器

    提供 JSON Schema 验证和自动修复能力。
    """

    def __init__(self, schema: Optional[Dict[str, Any]] = None):
        """初始化验证器

        Args:
            schema: JSON Schema，如果为 None 则使用默认的 CHECKPOINT_SCHEMA
        """
        self.schema = schema or CHECKPOINT_SCHEMA
        self.validator = jsonschema.Draft7Validator(self.schema)

    def validate(self, data: Dict[str, Any]) -> List[str]:
        """验证数据

        Args:
            data: 检查点数据

        Returns:
            错误消息列表，空表示验证通过
        """
        errors = []
        for error in self.validator.iter_errors(data):
            errors.append(f"{error.json_path}: {error.message}")
        return errors

    def repair(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """尝试修复数据

        Args:
            data: 检查点数据

        Returns:
            修复后的数据

        Raises:
            ValueError: 无法修复的数据
        """
        repaired = data.copy()

        # 1. 确保必填字段存在
        required_fields = ["workflow_id", "workflow_type", "status", "current_step",
                          "total_steps", "step_name", "input_data", "output_data",
                          "created_at", "updated_at"]
        for field in required_fields:
            if field not in repaired:
                if field == "error":
                    repaired[field] = None
                elif field in ["input_data", "output_data"]:
                    repaired[field] = {}
                elif field in ["current_step", "total_steps"]:
                    repaired[field] = 0
                elif field in ["created_at", "updated_at"]:
                    # 使用当前 UTC 时间
                    repaired[field] = datetime.now(timezone.utc).isoformat() + "Z"
                else:
                    raise ValueError(f"Cannot repair missing required field: {field}")

        # 2. 确保 status 是有效值
        valid_statuses = ["pending", "running", "completed", "failed", "cancelled"]
        if repaired["status"] not in valid_statuses:
            logger.warning(
                f"Invalid status '{repaired['status']}', setting to 'failed'"
            )
            repaired["status"] = "failed"

        # 3. 确保 current_step <= total_steps
        if repaired["current_step"] > repaired["total_steps"]:
            logger.warning(
                f"current_step ({repaired['current_step']}) > total_steps "
                f"({repaired['total_steps']}), capping to total_steps"
            )
            repaired["current_step"] = repaired["total_steps"]

        # 4. 确保 input_data 和 output_data 是 dict
        if not isinstance(repaired["input_data"], dict):
            repaired["input_data"] = {}
        if not isinstance(repaired["output_data"], dict):
            repaired["output_data"] = {}

        # 5. 移除 _crc32 字段（因为它会在保存时重新计算）
        repaired.pop("_crc32", None)

        return repaired

    def verify_crc32(self, data: Dict[str, Any]) -> bool:
        """验证 CRC32 校验和

        Args:
            data: 检查点数据（可能包含 _crc32 字段）

        Returns:
            True 表示校验通过，False 表示失败
        """
        stored_crc = data.get("_crc32")
        if stored_crc is None:
            logger.warning("No CRC32 found in checkpoint data")
            return False

        # 复制数据并移除 _crc32 字段
        data_copy = data.copy()
        data_copy.pop("_crc32", None)

        # 计算实际 CRC32
        content = json.dumps(data_copy, ensure_ascii=False).encode()
        actual_crc = zlib.crc32(content) & 0xffffffff

        if stored_crc != actual_crc:
            logger.error(
                f"CRC32 mismatch: stored={stored_crc:#06x}, actual={actual_crc:#06x}"
            )
            return False

        return True


def validate_checkpoint_file(path: Path, repair: bool = True) -> Optional[Dict[str, Any]]:
    """验证并可选修复检查点文件

    Args:
        path: 检查点文件路径
        repair: 是否尝试修复无效数据

    Returns:
        验证通过的检查点数据（可能已修复），失败返回 None
    """
    validator = CheckpointValidator()

    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Failed to load checkpoint {path}: {e}")
        return None

    # 验证
    errors = validator.validate(data)
    if errors:
        logger.warning(f"Checkpoint {path} validation errors: {errors}")

        if repair:
            logger.info(f"Attempting to repair checkpoint {path}")
            try:
                repaired = validator.repair(data)
                # 重新验证修复后的数据
                errors_after = validator.validate(repaired)
                if errors_after:
                    logger.error(f"Repair failed, still invalid: {errors_after}")
                    return None
                logger.info(f"Repair succeeded for checkpoint {path}")
                return repaired
            except ValueError as e:
                logger.error(f"Cannot repair checkpoint {path}: {e}")
                return None
        else:
            return None

    # 验证 CRC32
    if not validator.verify_crc32(data):
        logger.error(f"Checkpoint {path} CRC32 verification failed")
        if repair:
            # 去除 _crc32 并重新保存（重新计算）
            data_clean = data.copy()
            data_clean.pop("_crc32", None)
            return data_clean
        return None

    return data
