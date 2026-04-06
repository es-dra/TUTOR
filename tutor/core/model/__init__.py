"""TUTOR Model Gateway - 模型调用统一接口

支持两种配置方式：
1. 配置文件路径 (str) - 从 YAML 文件加载
2. 配置字典 (dict) - 直接传入配置
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
from requests.exceptions import RequestException, Timeout

# SecureConfig for encrypted API key storage
try:
    from tutor.core.secure_config import SecureConfig

    SECURE_CONFIG_AVAILABLE = True
except ImportError:
    SECURE_CONFIG_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """模型配置"""

    provider: str = "openai"
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""
    models: Optional[Dict[str, str]] = None
    fallback_models: Optional[Dict[str, List[str]]] = None
    max_retries: int = 3
    retry_base_delay: float = 1.0

    def __post_init__(self) -> None:
        if self.models is None:
            self.models = {}
        if self.fallback_models is None:
            self.fallback_models = {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelConfig":
        """从字典创建"""
        return cls(**data)


class ModelGateway:
    """模型网关 - 统一模型调用接口

    支持两种初始化方式：
    1. ModelGateway(config_path: str) - 从配置文件加载
    2. ModelGateway(config_dict: dict) - 直接传入配置字典
    3. ModelGateway(model_config: ModelConfig) - 传入配置对象

    默认配置：
    - provider: openai
    - api_base: https://api.openai.com/v1
    - models: {"default": "gpt-4o-mini"}

    环境变量：
    - OPENAI_API_KEY: API密钥
    - TUTOR_API_BASE: API基础URL
    """

    DEFAULT_MODELS = {
        "default": "gpt-4o-mini",
        "innovator": "gpt-4o",
        "synthesizer": "gpt-4o",
        "evaluator": "gpt-4o",
        "analyzer": "gpt-4o-mini",
        # Agent roles for multi-agent workflows
        "debate_a": "gpt-4o",
        "debate_b": "gpt-4o",
        "reviewer": "gpt-4o",
        "critic": "gpt-4o",
        "pragmatist": "gpt-4o",
        "expert": "gpt-4o",
        "coder": "gpt-4o",
        "skeptic": "gpt-4o",
        "writer": "gpt-4o",
        "planner": "gpt-4o",
        "judge": "gpt-4o",
        "meta_reviewer": "gpt-4o",
        "outliner": "gpt-4o",
        "debater_a": "gpt-4o",
        "debater_b": "gpt-4o",
        "analyst": "gpt-4o-mini",
        "supervisor": "gpt-4o",
        "executor": "gpt-4o-mini",
        "polisher": "gpt-4o-mini",
        "paper_loader": "gpt-4o-mini",
        "literature_searcher": "gpt-4o-mini",
        "orchestrator": "gpt-4o",
    }

    DEFAULT_FALLBACKS = {
        "default": ["gpt-4o-mini", "gpt-4o"],
        "innovator": ["gpt-4o", "gpt-4o-mini"],
        "synthesizer": ["gpt-4o", "gpt-4o-mini"],
        "evaluator": ["gpt-4o", "gpt-4o-mini"],
        "analyzer": ["gpt-4o-mini", "gpt-4o"],
        "debate_a": ["gpt-4o", "gpt-4o-mini"],
        "debate_b": ["gpt-4o", "gpt-4o-mini"],
        "reviewer": ["gpt-4o", "gpt-4o-mini"],
        "critic": ["gpt-4o", "gpt-4o-mini"],
        "pragmatist": ["gpt-4o", "gpt-4o-mini"],
        "expert": ["gpt-4o", "gpt-4o-mini"],
        "coder": ["gpt-4o", "gpt-4o-mini"],
        "skeptic": ["gpt-4o", "gpt-4o-mini"],
        "writer": ["gpt-4o", "gpt-4o-mini"],
        "planner": ["gpt-4o", "gpt-4o-mini"],
        "judge": ["gpt-4o", "gpt-4o-mini"],
        "meta_reviewer": ["gpt-4o", "gpt-4o-mini"],
        "outliner": ["gpt-4o", "gpt-4o-mini"],
        "debater_a": ["gpt-4o", "gpt-4o-mini"],
        "debater_b": ["gpt-4o", "gpt-4o-mini"],
        "analyst": ["gpt-4o-mini", "gpt-4o"],
        "supervisor": ["gpt-4o", "gpt-4o-mini"],
        "executor": ["gpt-4o-mini", "gpt-4o"],
        "polisher": ["gpt-4o-mini", "gpt-4o"],
        "paper_loader": ["gpt-4o-mini", "gpt-4o"],
        "literature_searcher": ["gpt-4o-mini", "gpt-4o"],
        "orchestrator": ["gpt-4o", "gpt-4o-mini"],
    }

    # Provider-specific model mappings (role -> model ID)
    PROVIDER_MODELS = {
        "deepseek": {
            "default": "deepseek-chat",
            "innovator": "deepseek-chat",
            "synthesizer": "deepseek-chat",
            "evaluator": "deepseek-chat",
            "analyzer": "deepseek-chat",
            "debate_a": "deepseek-chat",
            "debate_b": "deepseek-chat",
            "reviewer": "deepseek-chat",
            "critic": "deepseek-chat",
            "pragmatist": "deepseek-chat",
            "expert": "deepseek-chat",
            "skeptic": "deepseek-chat",
            "coder": "deepseek-coder",
        },
        "openai": DEFAULT_MODELS.copy(),
        "anthropic": {
            "default": "claude-sonnet-4-20250514",
            "innovator": "claude-sonnet-4-20250514",
            "synthesizer": "claude-sonnet-4-20250514",
            "evaluator": "claude-sonnet-4-20250514",
            "analyzer": "claude-sonnet-4-20250514",
            "skeptic": "claude-sonnet-4-20250514",
            "writer": "claude-sonnet-4-20250514",
            "planner": "claude-sonnet-4-20250514",
            "critic": "claude-sonnet-4-20250514",
            "reviewer": "claude-sonnet-4-20250514",
            "expert": "claude-sonnet-4-20250514",
            "coder": "claude-sonnet-4-20250514",
            "orchestrator": "claude-opus-4-20250414",
            "judge": "claude-opus-4-20250414",
            "meta_reviewer": "claude-opus-4-20250414",
            "debate_a": "claude-sonnet-4-20250514",
            "debate_b": "claude-sonnet-4-20250514",
            "pragmatist": "claude-sonnet-4-20250514",
            "outliner": "claude-sonnet-4-20250514",
            "debater_a": "claude-sonnet-4-20250514",
            "debater_b": "claude-sonnet-4-20250514",
            "analyst": "claude-sonnet-4-20250514",
            "supervisor": "claude-sonnet-4-20250514",
            "executor": "claude-sonnet-4-20250514",
            "polisher": "claude-sonnet-4-20250514",
            "paper_loader": "claude-sonnet-4-20250514",
            "literature_searcher": "claude-sonnet-4-20250514",
        },
    }

    # Role tier definitions - which tier each role belongs to
    # High: Core decision-making roles (use strongest model)
    # Medium: Analysis and debate roles
    # Low: Execution and support roles
    ROLE_TIERS = {
        "high": [
            "orchestrator",
            "judge",
            "planner",
            "meta_reviewer",
            "outliner",
            "innovator",
            "synthesizer",
            "evaluator",
        ],
        "medium": [
            "debater_a",
            "debater_b",
            "analyst",
            "writer",
            "supervisor",
            "reviewer",
            "expert",
            "skeptic",
        ],
        "low": [
            "executor",
            "polisher",
            "analyzer",
            "critic",
            "pragmatist",
            "coder",
            "paper_loader",
            "literature_searcher",
        ],
    }

    # Provider tier model mappings - which model ID to use for each tier
    # When only 1 model is available, all tiers use the same model
    # When multiple models are available, tiers can use different models
    PROVIDER_TIER_MODELS = {
        "deepseek": {
            "high": "deepseek-chat",
            "medium": "deepseek-chat",  # 单模型时全用同一个
            "low": "deepseek-chat",
        },
        "minimax": {
            "high": "minimax-chat",
            "medium": "minimax-chat",
            "low": "minimax-chat",
        },
        "openai": {
            "high": "gpt-4o",
            "medium": "gpt-4o-mini",
            "low": "gpt-4o-mini",
        },
        "anthropic": {
            "high": "claude-opus-4-20250414",
            "medium": "claude-sonnet-4-20250514",
            "low": "claude-sonnet-4-20250514",
        },
    }

    def __init__(
        self,
        config: Union[str, Dict[str, Any], ModelConfig, None] = None,
    ):
        self.config = self._load_config(config)
        self.api_base = self.config.api_base
        self.api_key = self.config.api_key
        # 使用配置中的 models，如果没有则根据 provider tier 选择默认模型
        # 注意：不要直接使用 PROVIDER_MODELS（包含显式角色映射），而是使用层级分配
        if self.config.models:
            # 用户显式提供了角色映射，使用用户的配置
            self.models = self.config.models
        else:
            # 使用层级分配，基于 tier_models 构建角色映射
            provider = (
                self.config.provider.lower() if self.config.provider else "openai"
            )
            if provider in self.PROVIDER_TIER_MODELS:
                tier_models = self.PROVIDER_TIER_MODELS[provider]
                # 构建完整角色->模型映射
                self.models = {}
                for tier, roles in self.ROLE_TIERS.items():
                    model = tier_models.get(
                        tier, tier_models.get("high", "gpt-4o-mini")
                    )
                    for role in roles:
                        self.models[role] = model
                # 添加 default 角色
                self.models["default"] = tier_models.get("high", "gpt-4o-mini")
            else:
                self.models = self.DEFAULT_MODELS.copy()

        # 使用配置中的 fallbacks，如果没有则使用默认
        if self.config.fallback_models:
            self.fallback_models = self.config.fallback_models
        else:
            # 根据 provider 选择默认 fallback
            provider = (
                self.config.provider.lower() if self.config.provider else "openai"
            )
            if provider == "deepseek":
                # DeepSeek 通常不需要 fallback
                self.fallback_models = {}
            else:
                self.fallback_models = self.DEFAULT_FALLBACKS.copy()
        self.max_retries = self.config.max_retries
        self.retry_base_delay = self.config.retry_base_delay

        # 如果没有设置 API key，尝试从环境变量获取
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY", "")

        # 如果没有设置 api_base，根据 provider 设置默认值
        if not self.api_base or self.api_base == "https://api.openai.com/v1":
            env_base = os.environ.get("TUTOR_API_BASE", "")
            if env_base:
                self.api_base = env_base
            else:
                # 根据 provider 设置默认 API base
                provider = (
                    self.config.provider.lower() if self.config.provider else "openai"
                )
                if provider == "deepseek":
                    self.api_base = "https://api.deepseek.com"
                elif provider == "minimax":
                    self.api_base = "https://api.minimax.chat/v1"
                elif provider == "anthropic":
                    self.api_base = "https://api.anthropic.com"
                # 否则保持默认的 OpenAI URL

        # 验证配置
        if not self.api_key:
            provider = (
                self.config.provider.lower() if self.config.provider else "openai"
            )
            if provider == "deepseek":
                env_key = os.environ.get("DEEPSEEK_API_KEY", "")
                if env_key:
                    self.api_key = env_key
                else:
                    logger.warning(
                        "DeepSeek API key not configured. Set DEEPSEEK_API_KEY environment variable "
                        "or provide api_key in config. Model calls will fail."
                    )
            elif provider == "minimax":
                env_key = os.environ.get("MINIMAX_API_KEY", "")
                if env_key:
                    self.api_key = env_key
                else:
                    logger.warning(
                        "Minimax API key not configured. Set MINIMAX_API_KEY environment variable "
                        "or provide api_key in config. Model calls will fail."
                    )
            else:
                logger.warning(
                    "API key not configured. Set OPENAI_API_KEY environment variable "
                    "or provide api_key in config. Model calls will fail."
                )

        logger.info(f"ModelGateway initialized with provider: {self.config.provider}")

    def _load_config(
        self, config: Union[str, Dict[str, Any], ModelConfig, None]
    ) -> ModelConfig:
        """加载配置

        Args:
            config: 可以是文件路径(str)、配置字典(dict)或ModelConfig对象

        Returns:
            ModelConfig对象
        """
        if config is None:
            # 尝试默认配置文件
            default_path = Path("config/config.yaml")
            if default_path.exists():
                return self._load_config_file(default_path)
            else:
                # 返回默认配置
                # 优先使用环境变量，然后尝试SecureConfig
                api_key = os.environ.get("OPENAI_API_KEY", "")
                if not api_key and SECURE_CONFIG_AVAILABLE:
                    # 尝试从SecureConfig获取（支持加密存储）
                    secure_config = SecureConfig()
                    api_key = secure_config.get("OPENAI_API_KEY", "")

                return ModelConfig(
                    provider="openai",
                    api_base=os.environ.get(
                        "TUTOR_API_BASE", "https://api.openai.com/v1"
                    ),
                    api_key=api_key,
                    models=self.DEFAULT_MODELS.copy(),
                )

        if isinstance(config, ModelConfig):
            return config

        if isinstance(config, dict):
            return ModelConfig.from_dict(config)

        if isinstance(config, str):
            # 如果是文件路径，加载文件
            config_path = Path(config)
            if config_path.exists():
                return self._load_config_file(config_path)
            else:
                # 可能是 API key 或 base URL，尝试解析
                return self._parse_simple_config(config)

        raise ValueError(f"Invalid config type: {type(config)}")

    def _load_config_file(self, config_path: Path) -> ModelConfig:
        """从YAML文件加载配置

        支持加密的API密钥存储。如果配置中使用 SecureConfig，
        API密钥会以加密形式存储，访问时自动解密。
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required to load config from file. "
                "Install with: pip install pyyaml"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        if cfg is None:
            cfg = {}

        model_cfg = cfg.get("model", {})

        # 获取 API key - 优先使用环境变量，然后是配置文件（可能是加密的）
        api_key = os.environ.get("OPENAI_API_KEY", "")

        # 如果环境变量没有，尝试从SecureConfig获取（支持加密存储）
        if not api_key and SECURE_CONFIG_AVAILABLE:
            config_file_key = model_cfg.get("api_key", "")
            if config_file_key:
                # 检查是否是加密格式
                if isinstance(config_file_key, str) and config_file_key.startswith(
                    "ENCRYPTED:"
                ):
                    # 使用SecureConfig解密
                    secure_config = SecureConfig()
                    api_key = secure_config.get("OPENAI_API_KEY", "")
                else:
                    api_key = config_file_key

        # 如果仍然没有API key，尝试从配置文件中的非加密字段获取
        if not api_key:
            api_key = model_cfg.get("api_key", "")

        return ModelConfig(
            provider=model_cfg.get("provider", "openai"),
            api_base=model_cfg.get(
                "api_base",
                os.environ.get("TUTOR_API_BASE", "https://api.openai.com/v1"),
            ),
            api_key=api_key,
            models=model_cfg.get("models", self.DEFAULT_MODELS.copy()),
        )

    def _parse_simple_config(self, config_str: str) -> ModelConfig:
        """解析简单配置字符串"""
        # 如果看起来像 API key
        if config_str.startswith("sk-") or config_str.startswith("sk-"):
            return ModelConfig(
                provider="openai",
                api_base=os.environ.get("TUTOR_API_BASE", "https://api.openai.com/v1"),
                api_key=config_str,
                models=self.DEFAULT_MODELS.copy(),
            )

        # 如果是 URL
        if config_str.startswith("http"):
            return ModelConfig(
                provider="openai",
                api_base=config_str,
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                models=self.DEFAULT_MODELS.copy(),
            )

        raise ValueError(f"Cannot parse config string: {config_str}")

    def chat(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """调用模型进行对话，支持重试和降级

        Args:
            model_name: 模型名称（如 'debate_a', 'evaluator'）
            messages: 消息列表，格式 [{"role": "user", "content": "..."}, ...]
            temperature: 温度参数
            max_tokens: 最大生成token数

        Returns:
            模型回复文本

        Raises:
            ModelError: 模型调用失败
        """
        resolved = self._resolve_model(model_name)
        if not resolved:
            raise ValueError(
                f"Unknown model name: {model_name}. "
                f"Available: {list(self.models.keys())}"
            )

        model_id, all_models = resolved

        # Try each model in sequence
        tried = []
        last_error = None

        for attempt_model_id in all_models:
            tried.append(attempt_model_id)
            retry_count = 0

            while retry_count <= self.max_retries:
                try:
                    return self._call_api(
                        attempt_model_id, messages, temperature, max_tokens
                    )
                except ModelError as e:
                    last_error = e
                    if self._is_retryable(e) and retry_count < self.max_retries:
                        delay = self.retry_base_delay * (2**retry_count)
                        logger.warning(
                            f"Retryable error for {attempt_model_id}, "
                            f"retrying in {delay:.1f}s (attempt {retry_count + 1}/{self.max_retries})"
                        )
                        time.sleep(delay)
                        retry_count += 1
                    else:
                        break

        # All models and retries exhausted
        logger.error(
            f"All models failed for '{model_name}'. Tried: {tried}. Last error: {last_error}"
        )
        raise ModelError(
            f"All models exhausted for '{model_name}'. Tried: {tried}. Last: {last_error}"
        )

    def _resolve_model(self, model_name: str) -> Optional[Tuple[str, List[str]]]:
        """解析模型名，返回(model_id, [fallback chain])"""
        if model_name not in self.models:
            if "default" in self.models:
                logger.warning(f"Model '{model_name}' not found, using 'default' model")
                model_name = "default"
            else:
                return None

        primary = self.models[model_name]
        fallbacks = self.fallback_models.get(model_name, [])

        # Dedupe while preserving order
        seen = {primary}
        chain = [primary]
        for fb in fallbacks:
            if fb not in seen:
                seen.add(fb)
                chain.append(fb)

        return primary, chain

    def _is_retryable(self, error: "ModelError") -> bool:
        """判断错误是否可重试"""
        msg = str(error).lower()
        # Timeout, rate limit, server errors are retryable
        retryable_keywords = [
            "timeout",
            "rate limit",
            "429",
            "500",
            "502",
            "503",
            "504",
            "service unavailable",
        ]
        return any(k in msg for k in retryable_keywords)

    # 模型费用配置（美元/1000 tokens）
    MODEL_COSTS = {
        # OpenAI 模型
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        # Anthropic 模型
        "claude-opus-4-20250414": {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        # 其他模型默认值
        "default": {"input": 0.001, "output": 0.002},
    }

    def __init__(
        self,
        config: Union[str, Dict[str, Any], ModelConfig, None] = None,
    ):
        self.config = self._load_config(config)
        self.api_base = self.config.api_base
        self.api_key = self.config.api_key
        # 使用配置中的 models，如果没有则根据 provider tier 选择默认模型
        # 注意：不要直接使用 PROVIDER_MODELS（包含显式角色映射），而是使用层级分配
        if self.config.models:
            # 用户显式提供了角色映射，使用用户的配置
            self.models = self.config.models
        else:
            # 使用层级分配，基于 tier_models 构建角色映射
            provider = (
                self.config.provider.lower() if self.config.provider else "openai"
            )
            if provider in self.PROVIDER_TIER_MODELS:
                tier_models = self.PROVIDER_TIER_MODELS[provider]
                # 构建完整角色->模型映射
                self.models = {}
                for tier, roles in self.ROLE_TIERS.items():
                    model = tier_models.get(
                        tier, tier_models.get("high", "gpt-4o-mini")
                    )
                    for role in roles:
                        self.models[role] = model
                # 添加 default 角色
                self.models["default"] = tier_models.get("high", "gpt-4o-mini")
            else:
                self.models = self.DEFAULT_MODELS.copy()

        # 使用配置中的 fallbacks，如果没有则使用默认
        if self.config.fallback_models:
            self.fallback_models = self.config.fallback_models
        else:
            # 根据 provider 选择默认 fallback
            provider = (
                self.config.provider.lower() if self.config.provider else "openai"
            )
            if provider == "deepseek":
                # DeepSeek 通常不需要 fallback
                self.fallback_models = {}
            else:
                self.fallback_models = self.DEFAULT_FALLBACKS.copy()
        self.max_retries = self.config.max_retries
        self.retry_base_delay = self.config.retry_base_delay

        # 如果没有设置 API key，尝试从环境变量获取
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY", "")

        # 如果没有设置 api_base，根据 provider 设置默认值
        if not self.api_base or self.api_base == "https://api.openai.com/v1":
            env_base = os.environ.get("TUTOR_API_BASE", "")
            if env_base:
                self.api_base = env_base
            else:
                # 根据 provider 设置默认 API base
                provider = (
                    self.config.provider.lower() if self.config.provider else "openai"
                )
                if provider == "deepseek":
                    self.api_base = "https://api.deepseek.com"
                elif provider == "minimax":
                    self.api_base = "https://api.minimax.chat/v1"
                elif provider == "anthropic":
                    self.api_base = "https://api.anthropic.com"
                # 否则保持默认的 OpenAI URL

        # 验证配置
        if not self.api_key:
            provider = (
                self.config.provider.lower() if self.config.provider else "openai"
            )
            if provider == "deepseek":
                env_key = os.environ.get("DEEPSEEK_API_KEY", "")
                if env_key:
                    self.api_key = env_key
                else:
                    logger.warning(
                        "DeepSeek API key not configured. Set DEEPSEEK_API_KEY environment variable "
                        "or provide api_key in config. Model calls will fail."
                    )
            elif provider == "minimax":
                env_key = os.environ.get("MINIMAX_API_KEY", "")
                if env_key:
                    self.api_key = env_key
                else:
                    logger.warning(
                        "Minimax API key not configured. Set MINIMAX_API_KEY environment variable "
                        "or provide api_key in config. Model calls will fail."
                    )
            else:
                logger.warning(
                    "API key not configured. Set OPENAI_API_KEY environment variable "
                    "or provide api_key in config. Model calls will fail."
                )

        # 费用追踪
        self.total_tokens = 0
        self.total_cost = 0.0
        self.token_usage_history = []

        logger.info(f"ModelGateway initialized with provider: {self.config.provider}")

    def get_model_cost(self, model_id: str) -> Dict[str, float]:
        """获取模型的费用配置"""
        for model_pattern, cost in self.MODEL_COSTS.items():
            if model_pattern in model_id:
                return cost
        return self.MODEL_COSTS["default"]

    def calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """计算费用"""
        cost_config = self.get_model_cost(model_id)
        input_cost = (input_tokens / 1000) * cost_config["input"]
        output_cost = (output_tokens / 1000) * cost_config["output"]
        return input_cost + output_cost

    def _call_api(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """执行实际的 API 调用"""
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(f"Calling model {model_id}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )

            # Handle rate limiting explicitly
            if response.status_code == 429:
                raise ModelError("Rate limit exceeded (429)")

            # Handle server errors
            if response.status_code >= 500:
                raise ModelError(f"Server error: {response.status_code}")

            response.raise_for_status()

            result = response.json()
            content: str = result["choices"][0]["message"]["content"]

            # 解析 token 使用情况
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            # 计算费用
            cost = self.calculate_cost(model_id, prompt_tokens, completion_tokens)

            # 更新费用追踪
            self.total_tokens += total_tokens
            self.total_cost += cost
            self.token_usage_history.append({
                "model_id": model_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost": cost,
                "timestamp": time.time(),
            })

            logger.info(f"Model {model_id} responded with {len(content)} chars")
            logger.info(f"Token usage: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}, cost=${cost:.4f}")
            logger.debug(f"Response: {content[:200]}...")

            return content

        except Timeout:
            logger.error(f"Model call timeout for {model_id}")
            raise ModelError(f"Timeout calling model {model_id}")
        except RequestException as e:
            logger.error(f"Model call failed for {model_id}: {e}")
            raise ModelError(f"Model call failed: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"Invalid response format for {model_id}: {e}")
            raise ModelError(f"Invalid response format: {e}")

    def get_usage_summary(self) -> Dict[str, Any]:
        """获取使用情况摘要"""
        return {
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "usage_history": self.token_usage_history,
        }

    def reset_usage(self) -> None:
        """重置使用情况追踪"""
        self.total_tokens = 0
        self.total_cost = 0.0
        self.token_usage_history = []
        logger.info("Usage tracking reset")

    def validate_connection(self) -> bool:
        """验证模型连接是否可用

        Returns:
            True 如果连接正常，False 否则
        """
        if not self.api_key:
            logger.warning("Cannot validate connection: no API key configured")
            return False

        try:
            response = requests.get(
                f"{self.api_base}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            success: bool = response.status_code == 200
            return success
        except Exception as e:
            logger.warning(f"Connection validation failed: {e}")
            return False

    def get_role_tier(self, role: str) -> str:
        """获取角色所属的层级

        Args:
            role: 角色名称

        Returns:
            tier: "high", "medium", 或 "low"
        """
        for tier, roles in self.ROLE_TIERS.items():
            if role in roles:
                return tier
        # 默认返回 medium（未知角色归入中等层级）
        return "medium"

    def assign_models_by_tier(
        self,
        tier_models: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """根据层级自动分配模型

        当只有1个模型时，所有角色共用该模型（通过不同 system prompt 区分）。
        当有多个模型时，按层级分配：
        - high tier: 核心决策角色 -> 最强模型
        - medium tier: 分析辩论角色 -> 中等模型
        - low tier: 执行支持角色 -> 轻量模型

        Args:
            tier_models: 可选，{tier: model_id} 格式的模型分配
                        如果不提供，则使用 PROVIDER_TIER_MODELS 的默认值

        Returns:
            {role: model_id} 格式的完整角色->模型映射
        """
        provider = self.config.provider.lower() if self.config.provider else "openai"
        default_tier_models = self.PROVIDER_TIER_MODELS.get(provider, {})

        if tier_models is None:
            tier_models = default_tier_models

        # 如果只有一个模型分配给某个 tier，其他 tier 也用同一个（单模型模式）
        # 找出实际分配的模型
        available_models = set(tier_models.values())
        if len(available_models) == 1:
            # 单模型模式：所有层都用同一个模型
            single_model = list(available_models)[0]
            tier_models = {
                "high": single_model,
                "medium": single_model,
                "low": single_model,
            }

        # 构建完整的角色->模型映射
        role_to_model = {}
        for tier, roles in self.ROLE_TIERS.items():
            model = tier_models.get(tier, tier_models.get("high", "gpt-4o-mini"))
            for role in roles:
                role_to_model[role] = model

        # 如果配置中有明确指定某些角色用特定模型，优先使用配置
        for role, model in self.models.items():
            if role in role_to_model:
                role_to_model[role] = model

        logger.info(
            f"Tier-based model assignment for {provider}: "
            f"high={tier_models.get('high', 'N/A')}, "
            f"medium={tier_models.get('medium', 'N/A')}, "
            f"low={tier_models.get('low', 'N/A')}"
        )

        return role_to_model

    def get_model_for_role(self, role: str) -> str:
        """获取指定角色应使用的模型

        Args:
            role: 角色名称

        Returns:
            模型 ID
        """
        if role in self.models:
            return self.models[role]

        # 如果没有明确配置，使用层级分配
        tier = self.get_role_tier(role)
        provider = self.config.provider.lower() if self.config.provider else "openai"
        tier_models = self.PROVIDER_TIER_MODELS.get(provider, {})
        return tier_models.get(tier, tier_models.get("high", "gpt-4o-mini"))

    def list_models(self) -> List[str]:
        """列出可用的模型名称"""
        return list(self.models.keys())


class ModelError(Exception):
    """模型调用异常"""

    pass


# 便捷函数
def create_gateway(
    config: Union[str, Dict[str, Any], ModelConfig, None] = None,
) -> ModelGateway:
    """创建 ModelGateway 实例的便捷函数"""
    return ModelGateway(config)


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    try:
        gateway = ModelGateway()
        print(
            f"Config: provider={gateway.config.provider}, api_base={gateway.api_base}"
        )
        print(f"Available models: {gateway.list_models()}")

        if gateway.validate_connection():
            print("✓ Model connection OK")
        else:
            print("⚠ Model connection not validated (may need API key)")

    except Exception as e:
        print(f"Error: {e}")
