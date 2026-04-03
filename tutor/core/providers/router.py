"""Provider Router - 智能路由与负载均衡

支持多种路由策略：
- priority: 按优先级选择 Provider
- failover: 主 Provider 失败时自动切换
- loadbalance: 轮询负载均衡
- cost-optimize: 按成本优化（未来扩展）
"""

import logging
import random
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from threading import Lock

from .base import BaseProvider, ProviderConfig, ProviderError

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """路由配置"""
    strategy: str = "priority"  # priority | failover | loadbalance | cost-optimize
    fallback_enabled: bool = True
    retry_on_failure: bool = True
    max_retries: int = 3
    health_check_interval: int = 300  # 健康检查间隔（秒）


class ProviderRouter:
    """Provider 路由器

    管理多个 Provider，支持故障切换和负载均衡。
    """

    # Provider 注册表
    _provider_registry: Dict[str, type] = {}

    @classmethod
    def register_provider(cls, name: str) -> Callable:
        """注册 Provider 类（装饰器）

        Usage:
            @ProviderRouter.register_provider("openai")
            class OpenAIProvider(BaseProvider):
                ...
        """
        def decorator(provider_class: type) -> type:
            cls._provider_registry[name] = provider_class
            return provider_class
        return decorator

    def __init__(
        self,
        providers: List[BaseProvider],
        config: Optional[RouterConfig] = None,
    ):
        """初始化路由器

        Args:
            providers: Provider 实例列表
            config: 路由配置
        """
        self.providers = providers
        self.config = config or RouterConfig()
        self._lock = Lock()
        self._round_robin_index = 0

        # 按优先级排序
        self.providers = sorted(self.providers, key=lambda p: getattr(p, 'priority', 1))

    @classmethod
    def create_from_config(cls, configs: List[ProviderConfig]) -> "ProviderRouter":
        """从配置创建路由器

        Args:
            configs: Provider 配置列表

        Returns:
            ProviderRouter 实例
        """
        providers = []

        for cfg in sorted(configs):  # 按 priority 排序
            if not cfg.enabled:
                continue

            if cfg.name not in cls._provider_registry:
                logger.warning(f"Unknown provider: {cfg.name}, skipping")
                continue

            provider_class = cls._provider_registry[cfg.name]
            provider = provider_class(
                api_key=cfg.api_key,
                api_base=cfg.api_base,
                models=cfg.models,
                priority=cfg.priority,
                api_version=getattr(cfg, 'api_version', None),
                deployment_name=getattr(cfg, 'deployment_name', None),
            )
            providers.append(provider)

        return cls(providers=providers)

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        preferred_provider: Optional[str] = None,
        **kwargs
    ) -> str:
        """发送聊天请求

        Args:
            model: 模型名称
            messages: 消息列表
            preferred_provider: 首选 Provider（可选）
            **kwargs: 其他参数

        Returns:
            生成的文本内容
        """
        if not self.providers:
            raise ProviderError("No providers available")

        # 根据策略选择 Provider
        if preferred_provider:
            selected = self._select_provider_by_name(preferred_provider)
            if selected:
                return selected.chat(model, messages, **kwargs)
            logger.warning(f"Preferred provider '{preferred_provider}' not available")

        # 路由策略
        strategy = self.config.strategy

        if strategy == "priority":
            return self._chat_priority(model, messages, **kwargs)
        elif strategy == "failover":
            return self._chat_failover(model, messages, **kwargs)
        elif strategy == "loadbalance":
            return self._chat_loadbalance(model, messages, **kwargs)
        elif strategy == "cost-optimize":
            return self._chat_priority(model, messages, **kwargs)  # 暂用 priority
        else:
            logger.warning(f"Unknown strategy '{strategy}', using priority")
            return self._chat_priority(model, messages, **kwargs)

    def _select_provider_by_name(self, name: str) -> Optional[BaseProvider]:
        """根据名称选择 Provider"""
        for p in self.providers:
            if p.get_provider_name() == name:
                return p
        return None

    def _select_first_available(self) -> Optional[BaseProvider]:
        """选择第一个可用的 Provider"""
        for provider in self.providers:
            try:
                if provider.validate_connection():
                    return provider
            except Exception:
                continue
        return self.providers[0] if self.providers else None

    def _chat_priority(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """优先级策略：总是使用最高优先级 Provider"""
        for provider in self.providers:
            try:
                return provider.chat(model, messages, **kwargs)
            except Exception as e:
                logger.warning(f"Provider {provider.get_provider_name()} failed: {e}")
                if not self.config.fallback_enabled:
                    raise
                continue

        raise ProviderError("All providers failed")

    def _chat_failover(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """故障切换策略：尝试主 Provider，失败后切换"""
        last_error = None

        for i, provider in enumerate(self.providers):
            try:
                return provider.chat(model, messages, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Provider {provider.get_provider_name()} (attempt {i+1}) failed: {e}"
                )
                if not self.config.fallback_enabled:
                    raise

        raise last_error or ProviderError("All providers failed")

    def _chat_loadbalance(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """负载均衡策略：轮询选择 Provider"""
        n = len(self.providers)

        for _ in range(n):  # 最多尝试 n 次
            with self._lock:
                idx = self._round_robin_index
                self._round_robin_index = (self._round_robin_index + 1) % n

            provider = self.providers[idx]
            try:
                return provider.chat(model, messages, **kwargs)
            except Exception as e:
                logger.warning(f"Provider {provider.get_provider_name()} failed: {e}")
                continue

        raise ProviderError("All providers failed")

    def validate_connections(self) -> Dict[str, bool]:
        """验证所有 Provider 连接

        Returns:
            {provider_name: is_connected}
        """
        results = {}
        for provider in self.providers:
            try:
                results[provider.get_provider_name()] = provider.validate_connection()
            except Exception as e:
                logger.warning(f"Connection check failed for {provider.get_provider_name()}: {e}")
                results[provider.get_provider_name()] = False
        return results

    def get_provider_status(self) -> List[Dict[str, Any]]:
        """获取所有 Provider 状态

        Returns:
            Provider 状态列表
        """
        status = []
        for provider in self.providers:
            name = provider.get_provider_name()
            try:
                is_connected = provider.validate_connection()
            except Exception:
                is_connected = False

            status.append({
                "name": name,
                "connected": is_connected,
                "priority": getattr(provider, 'priority', 1),
                "default_model": provider.get_default_model(),
            })
        return status

    def add_provider(self, provider: BaseProvider) -> None:
        """添加 Provider"""
        with self._lock:
            self.providers.append(provider)
            self.providers = sorted(self.providers, key=lambda p: getattr(p, 'priority', 1))

    def remove_provider(self, name: str) -> bool:
        """移除 Provider

        Returns:
            是否成功移除
        """
        with self._lock:
            for i, p in enumerate(self.providers):
                if p.get_provider_name() == name:
                    self.providers.pop(i)
                    return True
        return False

    def get_available_providers(self) -> List[str]:
        """获取可用的 Provider 名称列表"""
        return [p.get_provider_name() for p in self.providers]
