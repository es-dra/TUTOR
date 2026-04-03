"""TUTOR Debate Module - 跨模型辩论框架

核心组件:
- ModelAssignmentConfig: 模块级模型配置
- CrossModelDebater: 跨模型辩论编排器
- DebateRole: 辩论角色定义
"""

from .model_config import (
    DebateRole,
    ModelAssignment,
    ModuleModelConfig,
    RoleModelAssignment,
    DebateModelConfig,
    get_default_debate_config,
    create_user_config,
    MODEL_VENDOR_MAP,
)
from .cross_model_debater import (
    CrossModelDebater,
    DebateTurn,
    DebateResult,
    ModelResponse,
    create_cross_model_debater,
)

__all__ = [
    # Enums
    "DebateRole",
    # Config
    "ModelAssignment",
    "ModuleModelConfig",
    "RoleModelAssignment",
    "DebateModelConfig",
    "get_default_debate_config",
    "create_user_config",
    "MODEL_VENDOR_MAP",
    # Orchestrator
    "CrossModelDebater",
    "DebateTurn",
    "DebateResult",
    "ModelResponse",
    "create_cross_model_debater",
]