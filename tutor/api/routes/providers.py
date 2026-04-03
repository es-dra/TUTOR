"""Provider Configuration API Routes

提供 Provider 配置管理端点：
- GET /api/v1/providers - 获取所有 Provider 状态
- GET /api/v1/providers/{name} - 获取特定 Provider 配置
- PUT /api/v1/providers/{name} - 更新 Provider 配置
- POST /api/v1/providers/{name}/validate - 验证 Provider 连接
"""

import os
import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from tutor.core.providers import (
    OpenAIProvider,
    DeepSeekProvider,
    AnthropicProvider,
    AzureProvider,
    LocalProvider,
    MinimaxProvider,
    ProviderRouter,
    ProviderConfig,
)
from tutor.core.secure_config import SecureConfig

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])

# Provider 列表
PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "anthropic": AnthropicProvider,
    "azure": AzureProvider,
    "local": LocalProvider,
    "minimax": MinimaxProvider,
}

# 全局配置管理器（延迟初始化）
_config_manager: Optional["ProviderConfigManager"] = None


class ProviderConfigManager:
    """Provider 配置管理器 - 持久化存储 API Keys"""

    def __init__(self, config_path: str = "config/providers.yaml"):
        self.config_path = config_path
        self._secure_config: Optional[SecureConfig] = None
        self._provider_configs: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载配置"""
        if not os.path.exists(self.config_path):
            # 使用默认配置
            self._provider_configs = self._default_configs()
            return

        try:
            self._secure_config = SecureConfig.load(
                self.config_path,
                master_key=os.environ.get("TUTOR_MASTER_KEY", "")
            )
            # 加载每个 Provider 的配置
            for name in PROVIDER_CLASSES:
                self._provider_configs[name] = {
                    "api_key": self._secure_config.get(f"{name}_api_key", ""),
                    "api_base": self._secure_config.get(f"{name}_api_base", ""),
                    "enabled": True,
                    "priority": 1,
                    "models": {},
                }
        except Exception as e:
            logger.warning(f"Failed to load provider config: {e}")
            self._provider_configs = self._default_configs()

    def _default_configs(self) -> Dict[str, Dict[str, Any]]:
        """默认配置"""
        configs = {}
        for name, cls in PROVIDER_CLASSES.items():
            try:
                instance = cls(api_key="")
                configs[name] = {
                    "api_key": "",
                    "api_base": getattr(instance, 'api_base', '') or getattr(instance, 'DEFAULT_API_BASE', ''),
                    "enabled": True,
                    "priority": 1,
                    "models": getattr(instance, 'models', {}) or getattr(instance, 'DEFAULT_MODELS', {}),
                }
            except Exception:
                configs[name] = {
                    "api_key": "",
                    "api_base": "",
                    "enabled": True,
                    "priority": 1,
                    "models": {},
                }
        return configs

    def get_provider_config(self, name: str) -> Dict[str, Any]:
        """获取 Provider 配置"""
        return self._provider_configs.get(name, {})

    def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """获取所有配置"""
        return self._provider_configs.copy()

    def update_provider(self, name: str, api_key: str = "", api_base: str = "", **kwargs) -> Dict[str, Any]:
        """更新 Provider 配置（加密存储）"""
        if name not in self._provider_configs:
            raise ValueError(f"Unknown provider: {name}")

        # 初始化 SecureConfig（如果需要保存）
        if api_key and not self._secure_config:
            self._secure_config = SecureConfig(master_key=os.environ.get("TUTOR_MASTER_KEY", ""))

        # 保存加密的 API Key
        if api_key:
            if self._secure_config and self._secure_config._master_key:
                self._secure_config.set_encrypted(f"{name}_api_key", api_key)
            else:
                # 无加密密钥时直接存储（仅开发模式）
                self._provider_configs[name]["api_key"] = api_key

        if api_base:
            self._provider_configs[name]["api_base"] = api_base

        for key, value in kwargs.items():
            if key in ("enabled", "priority", "models"):
                self._provider_configs[name][key] = value

        # 持久化
        self._save()

        return self._provider_configs[name]

    def _save(self) -> None:
        """保存配置到文件"""
        if not self._secure_config:
            return

        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            # 保存加密数据
            for name, config in self._provider_configs.items():
                if config.get("api_key"):
                    self._secure_config.set(f"{name}_api_key", config["api_key"])
                if config.get("api_base"):
                    self._secure_config.set(f"{name}_api_base", config["api_base"])
            self._secure_config.save(self.config_path)
        except Exception as e:
            logger.warning(f"Failed to save provider config: {e}")

    def get_api_key(self, name: str) -> str:
        """获取解密的 API Key"""
        config = self._provider_configs.get(name, {})
        api_key = config.get("api_key", "")

        # 如果是加密格式，尝试解密
        if api_key.startswith("ENCRYPTED:") and self._secure_config:
            try:
                return self._secure_config.get(f"{name}_api_key", "")
            except Exception:
                return ""
        return api_key


def get_config_manager() -> ProviderConfigManager:
    """获取全局配置管理器（单例）"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ProviderConfigManager()
    return _config_manager


class ProviderStatus(BaseModel):
    """Provider 状态"""
    name: str
    enabled: bool
    connected: bool
    priority: int
    default_model: Optional[str] = None
    api_base: Optional[str] = None
    models: Dict[str, str] = {}


class ProviderConfigUpdate(BaseModel):
    """Provider 配置更新"""
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    deployment_name: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    models: Optional[Dict[str, str]] = None


class ValidationResult(BaseModel):
    """验证结果"""
    provider: str
    success: bool
    message: str


@router.get("", response_model=Dict[str, ProviderStatus])
async def list_providers():
    """获取所有 Provider 的状态

    Returns:
        所有 Provider 的状态列表
    """
    mgr = get_config_manager()
    providers = {}

    for name in PROVIDER_CLASSES:
        cfg = mgr.get_provider_config(name)
        api_key = mgr.get_api_key(name)

        # 创建实例进行验证
        try:
            cls = PROVIDER_CLASSES[name]
            instance = cls(
                api_key=api_key or "dummy",
                api_base=cfg.get("api_base", "")
            )
            connected = instance.validate_connection() if api_key else False
            providers[name] = ProviderStatus(
                name=name,
                enabled=cfg.get("enabled", True),
                connected=connected,
                priority=cfg.get("priority", 1),
                default_model=instance.get_default_model(),
                api_base=cfg.get("api_base", ""),
                models=cfg.get("models", {}),
            )
        except Exception as e:
            providers[name] = ProviderStatus(
                name=name,
                enabled=cfg.get("enabled", True),
                connected=False,
                priority=cfg.get("priority", 1),
            )

    return providers


@router.get("/{provider_name}", response_model=ProviderStatus)
async def get_provider(provider_name: str):
    """获取特定 Provider 的配置

    Args:
        provider_name: Provider 名称

    Returns:
        Provider 配置
    """
    if provider_name not in PROVIDER_CLASSES:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_name}' not found. Available: {list(PROVIDER_CLASSES.keys())}"
        )

    mgr = get_config_manager()
    cfg = mgr.get_provider_config(provider_name)
    api_key = mgr.get_api_key(provider_name)

    cls = PROVIDER_CLASSES[provider_name]
    instance = cls(api_key=api_key or "dummy", api_base=cfg.get("api_base", ""))

    connected = instance.validate_connection() if api_key else False

    return ProviderStatus(
        name=provider_name,
        enabled=cfg.get("enabled", True),
        connected=connected,
        priority=cfg.get("priority", 1),
        default_model=instance.get_default_model(),
        api_base=cfg.get("api_base", ""),
        models=cfg.get("models", {}),
    )


@router.put("/{provider_name}", response_model=ProviderStatus)
async def update_provider(
    provider_name: str,
    config: ProviderConfigUpdate,
):
    """更新 Provider 配置（持久化到本地文件）

    Args:
        provider_name: Provider 名称
        config: 新的配置

    Returns:
        更新后的 Provider 配置
    """
    if provider_name not in PROVIDER_CLASSES:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_name}' not found"
        )

    mgr = get_config_manager()

    # 更新配置
    updated = mgr.update_provider(
        provider_name,
        api_key=config.api_key or "",
        api_base=config.api_base or "",
        priority=config.priority,
        enabled=config.enabled,
        models=config.models,
    )

    # 获取实例进行验证
    api_key = mgr.get_api_key(provider_name)
    cls = PROVIDER_CLASSES[provider_name]
    instance = cls(api_key=api_key or "dummy", api_base=updated.get("api_base", ""))
    connected = instance.validate_connection() if api_key else False

    return ProviderStatus(
        name=provider_name,
        enabled=updated.get("enabled", True),
        connected=connected,
        priority=updated.get("priority", 1),
        default_model=instance.get_default_model(),
        api_base=updated.get("api_base", ""),
        models=updated.get("models", {}),
    )


@router.post("/{provider_name}/validate", response_model=ValidationResult)
async def validate_provider(
    provider_name: str,
    api_key: str = "",
    api_base: str = "",
):
    """验证 Provider 连接（验证成功后会保存 API Key）

    Args:
        provider_name: Provider 名称
        api_key: API Key（可选，验证成功后会保存）
        api_base: API Base URL（可选）

    Returns:
        验证结果
    """
    if provider_name not in PROVIDER_CLASSES:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_name}' not found"
        )

    mgr = get_config_manager()
    cls = PROVIDER_CLASSES[provider_name]

    # 优先使用提供的 API Key，否则使用存储的
    if not api_key:
        api_key = mgr.get_api_key(provider_name)
    if not api_base:
        cfg = mgr.get_provider_config(provider_name)
        api_base = cfg.get("api_base", "")

    try:
        instance = cls(api_key=api_key, api_base=api_base)
        connected = instance.validate_connection()

        # 验证成功，保存 API Key
        if connected and api_key:
            mgr.update_provider(provider_name, api_key=api_key, api_base=api_base)

        return ValidationResult(
            provider=provider_name,
            success=connected,
            message="Connection successful" if connected else "Connection failed",
        )

    except Exception as e:
        return ValidationResult(
            provider=provider_name,
            success=False,
            message=f"Error: {str(e)}",
        )


@router.get("/supported/models", response_model=List[str])
async def list_supported_models():
    """获取所有支持的模型

    Returns:
        所有支持的模型列表
    """
    models = []
    for name, cls in PROVIDER_CLASSES.items():
        try:
            instance = cls(api_key="dummy")
            if hasattr(instance, 'DEFAULT_MODELS'):
                models.extend(instance.DEFAULT_MODELS.values())
        except Exception:
            pass

    return list(set(models))
