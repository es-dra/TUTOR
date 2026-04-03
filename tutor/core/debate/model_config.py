"""模型配置 - 支持用户自定义和模块级模型分配

设计原则:
1. 每个辩论角色可有多个模型(异构辩论)
2. 单模型时自动回退到"生成+批判"同模型模式
3. 用户可完全自定义，保留各模块推荐默认值
4. 支持模型别名(如 "claude", "gpt4", "gemini")
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class DebateRole(Enum):
    """辩论角色枚举"""
    INNOVATOR = "innovator"      # 创新者 - 提出新想法
    SKEPTIC = "skeptic"          # 怀疑者 - 批判性评审
    PRAGMATIST = "pragmatist"    # 务实者 - 评估可行性
    EXPERT = "expert"            # 专家 - 提供领域知识
    SYNTHESIZER = "synthesizer"  # 综合者 - 汇总结论
    CRITIC = "critic"            # 批评者 - 对抗性评审
    ADVOCATE = "advocate"        # 辩护者 - 为想法辩护


# 各模块推荐模型配置 (默认推荐)
DEFAULT_MODEL_RECOMMENDATIONS = {
    "idea_debate": {
        "innovator": ["claude-sonnet-4", "gpt-4o"],
        "skeptic": ["gpt-4o", "gemini-2-5-pro"],
        "pragmatist": ["claude-sonnet-4", "gemini-2-5-pro"],
        "expert": ["gpt-4o", "claude-sonnet-4"],
        "synthesizer": ["claude-sonnet-4", "gpt-4o"],
    },
    "paper_review": {
        "advocate": ["claude-sonnet-4", "gpt-4o"],
        "critic": ["gpt-4o", "gemini-2-5-pro"],
        "synthesizer": ["claude-sonnet-4", "gpt-4o"],
    },
    "literature_review": {
        "analyzer": ["gpt-4o", "claude-sonnet-4"],
        "synthesizer": ["claude-sonnet-4", "gpt-4o"],
    },
    "experiment_design": {
        "planner": ["claude-sonnet-4", "gpt-4o"],
        "critic": ["gpt-4o", "gemini-2-5-pro"],
        "synthesizer": ["claude-sonnet-4", "gpt-4o"],
    },
}

# 模型厂商映射 (用于检测是否同厂商)
MODEL_VENDOR_MAP = {
    # Anthropic
    "claude": "anthropic",
    "claude-sonnet-4": "anthropic",
    "claude-opus-4": "anthropic",
    "claude-3-5-sonnet": "anthropic",
    "claude-3-5-sonnet-20241022": "anthropic",
    # OpenAI
    "gpt-4": "openai",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-3.5-turbo": "openai",
    # Google
    "gemini": "google",
    "gemini-2-5-pro": "google",
    "gemini-2-5-flash": "google",
    # DeepSeek
    "deepseek": "deepseek",
    "deepseek-chat": "deepseek",
    # Other
    "llama": "meta",
    "qwen": "alibaba",
}


@dataclass
class ModelAssignment:
    """单个模型分配

    Attributes:
        model_id: 模型标识符 (如 "claude-sonnet-4", "gpt-4o")
        temperature: 生成温度 (默认0.7, 创新者可用更高)
        max_tokens: 最大生成token数
        custom_prompt_suffix: 用户自定义的prompt后缀
    """
    model_id: str
    temperature: float = 0.7
    max_tokens: int = 2000
    custom_prompt_suffix: str = ""

    @property
    def vendor(self) -> str:
        """获取模型厂商"""
        model_lower = self.model_id.lower()
        for key, vendor in MODEL_VENDOR_MAP.items():
            if key in model_lower:
                return vendor
        return "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "custom_prompt_suffix": self.custom_prompt_suffix,
        }


@dataclass
class RoleModelAssignment:
    """单个辩论角色的模型分配

    支持多模型(异构模式)或单模型(单模型回退模式)

    Attributes:
        role: 辩论角色
        models: 分配的模型列表
            - 1个模型: 单模型回退模式 (生成+批判由同一模型完成)
            - 2+个模型: 异构辩论模式 (每个模型一个实例)
        prompt_template: 角色prompt模板 (可选)
    """
    role: DebateRole
    models: List[ModelAssignment] = field(default_factory=list)
    prompt_template: str = ""

    @property
    def is_heterogeneous(self) -> bool:
        """是否异构模式 (多模型)"""
        return len(self.models) >= 2

    @property
    def is_single_model(self) -> bool:
        """是否单模型模式"""
        return len(self.models) == 1

    @property
    def primary_model(self) -> Optional[ModelAssignment]:
        """主模型 (第一个)"""
        return self.models[0] if self.models else None

    def get_model_vendors(self) -> List[str]:
        """获取所有模型的厂商列表"""
        return [m.vendor for m in self.models]

    def has_vendor_diversity(self) -> bool:
        """是否有厂商多样性"""
        vendors = set(self.get_model_vendors())
        return len(vendors) > 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "models": [m.to_dict() for m in self.models],
            "is_heterogeneous": self.is_heterogeneous,
            "prompt_template": self.prompt_template,
        }


@dataclass
class ModuleModelConfig:
    """模块级模型配置

    用户可以为每个工作流模块配置不同的模型组合

    Attributes:
        module_name: 模块名称 (如 "idea_debate", "paper_review")
        role_assignments: 各角色的模型分配
        debate_rounds: 辩论轮数 (默认2)
        enable_cross_examination: 是否启用交叉质询 (默认True)
        require_vendor_diversity: 是否强制要求厂商多样性 (默认False)
    """
    module_name: str
    role_assignments: List[RoleModelAssignment] = field(default_factory=list)
    debate_rounds: int = 2
    enable_cross_examination: bool = True
    require_vendor_diversity: bool = False

    def get_role(self, role: DebateRole) -> Optional[RoleModelAssignment]:
        """获取指定角色的模型分配"""
        for assignment in self.role_assignments:
            if assignment.role == role:
                return assignment
        return None

    def get_all_models(self) -> List[ModelAssignment]:
        """获取所有配置的模型 (去重)"""
        all_models = []
        seen = set()
        for assignment in self.role_assignments:
            for model in assignment.models:
                if model.model_id not in seen:
                    seen.add(model.model_id)
                    all_models.append(model)
        return all_models

    def get_unique_vendors(self) -> List[str]:
        """获取所有涉及的不同厂商"""
        vendors = set()
        for assignment in self.role_assignments:
            vendors.update(assignment.get_model_vendors())
        return list(vendors)

    def validate(self) -> List[str]:
        """验证配置合法性

        Returns:
            错误列表，空表示配置有效
        """
        errors = []

        if not self.role_assignments:
            errors.append(f"Module '{self.module_name}': No role assignments configured")

        # 检查必需角色
        required_roles = {DebateRole.INNOVATOR, DebateRole.SKEPTIC, DebateRole.SYNTHESIZER}
        configured_roles = {a.role for a in self.role_assignments}
        missing_roles = required_roles - configured_roles
        if missing_roles:
            errors.append(f"Missing required roles: {[r.value for r in missing_roles]}")

        # 检查厂商多样性
        if self.require_vendor_diversity:
            vendors = self.get_unique_vendors()
            if len(vendors) < 2:
                errors.append(f"Vendor diversity required but only {vendors} configured")

        return errors

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModuleModelConfig":
        """从字典创建配置"""
        module_name = data.get("module_name", "default")
        role_assignments = []

        for role_str, models_data in data.get("role_assignments", {}).items():
            try:
                role = DebateRole(role_str)
            except ValueError:
                continue

            models = []
            if isinstance(models_data, str):
                # 单模型字符串 "gpt-4o"
                models = [ModelAssignment(model_id=models_data)]
            elif isinstance(models_data, list):
                # 模型列表 ["gpt-4o", "claude-sonnet-4"]
                models = [ModelAssignment(model_id=m) if isinstance(m, str) else ModelAssignment(**m)
                         for m in models_data]
            elif isinstance(models_data, dict):
                # 详细配置 {"models": [...], "prompt_template": "..."}
                models_list = models_data.get("models", [])
                models = [ModelAssignment(model_id=m) if isinstance(m, str) else ModelAssignment(**m)
                         for m in models_list]

            role_assignments.append(RoleModelAssignment(
                role=role,
                models=models,
                prompt_template=models_data.get("prompt_template", "") if isinstance(models_data, dict) else "",
            ))

        return cls(
            module_name=module_name,
            role_assignments=role_assignments,
            debate_rounds=data.get("debate_rounds", 2),
            enable_cross_examination=data.get("enable_cross_examination", True),
            require_vendor_diversity=data.get("require_vendor_diversity", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_name": self.module_name,
            "role_assignments": {
                a.role.value: {
                    "models": [m.model_id for m in a.models],
                    "prompt_template": a.prompt_template,
                }
                for a in self.role_assignments
            },
            "debate_rounds": self.debate_rounds,
            "enable_cross_examination": self.enable_cross_examination,
            "require_vendor_diversity": self.require_vendor_diversity,
        }


@dataclass
class DebateModelConfig:
    """辩论模型总配置

    包含多个模块的配置，支持完整的研究流程
    """
    modules: Dict[str, ModuleModelConfig] = field(default_factory=dict)
    global_fallback_models: List[str] = field(default_factory=list)

    def get_module_config(self, module_name: str) -> Optional[ModuleModelConfig]:
        """获取指定模块配置"""
        return self.modules.get(module_name)

    def get_or_create_module(self, module_name: str) -> ModuleModelConfig:
        """获取或创建模块配置"""
        if module_name not in self.modules:
            self.modules[module_name] = ModuleModelConfig(module_name=module_name)
        return self.modules[module_name]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateModelConfig":
        """从字典创建配置"""
        modules = {}
        for module_name, module_data in data.get("modules", {}).items():
            if isinstance(module_data, dict):
                modules[module_name] = ModuleModelConfig.from_dict({
                    "module_name": module_name,
                    **module_data
                })
        return cls(
            modules=modules,
            global_fallback_models=data.get("global_fallback_models", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modules": {
                name: config.to_dict()
                for name, config in self.modules.items()
            },
            "global_fallback_models": self.global_fallback_models,
        }


def get_default_debate_config(module_name: str = "idea_debate") -> ModuleModelConfig:
    """获取指定模块的默认推荐配置

    Args:
        module_name: 模块名称

    Returns:
        默认模型配置 (包含推荐模型)
    """
    recommendations = DEFAULT_MODEL_RECOMMENDATIONS.get(
        module_name,
        DEFAULT_MODEL_RECOMMENDATIONS["idea_debate"]
    )

    role_assignments = []
    for role_str, model_ids in recommendations.items():
        try:
            role = DebateRole(role_str)
        except ValueError:
            continue

        models = [ModelAssignment(model_id=mid) for mid in model_ids]
        role_assignments.append(RoleModelAssignment(
            role=role,
            models=models,
        ))

    return ModuleModelConfig(
        module_name=module_name,
        role_assignments=role_assignments,
        debate_rounds=2,
        enable_cross_examination=True,
        require_vendor_diversity=False,
    )


def create_user_config(
    module_name: str,
    role_model_map: Dict[str, List[str]],
    debate_rounds: int = 2,
    **kwargs
) -> ModuleModelConfig:
    """创建用户自定义配置的便捷函数

    Args:
        module_name: 模块名称
        role_model_map: 角色到模型的映射
            例如: {"innovator": ["claude-sonnet-4"], "skeptic": ["gpt-4o"]}
        debate_rounds: 辩论轮数

    Example:
        config = create_user_config(
            "idea_debate",
            {"innovator": ["claude"], "skeptic": ["gpt-4o"]}
        )
    """
    role_assignments = []
    for role_str, model_ids in role_model_map.items():
        try:
            role = DebateRole(role_str)
        except ValueError:
            continue

        models = [ModelAssignment(model_id=mid) for mid in model_ids]
        role_assignments.append(RoleModelAssignment(
            role=role,
            models=models,
        ))

    return ModuleModelConfig(
        module_name=module_name,
        role_assignments=role_assignments,
        debate_rounds=debate_rounds,
        **kwargs
    )
