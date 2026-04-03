"""Base Provider 抽象基类

所有 Provider 必须实现的接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
import logging
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResponse:
    """聊天响应"""
    content: str
    provider: str
    model: str
    usage: Optional[Dict[str, Any]] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class ProviderConfig:
    """Provider 配置"""
    name: str
    api_key: str = ""
    api_base: str = ""
    api_version: str = "2023-05-15"  # Azure API 版本
    deployment_name: str = ""  # Azure deployment
    models: Dict[str, str] = field(default_factory=dict)
    priority: int = 1  # 优先级，数字越小优先级越高
    enabled: bool = True
    max_retries: int = 3
    timeout: int = 60

    def __lt__(self, other: "ProviderConfig"):
        """按 priority 排序"""
        return self.priority < other.priority


class BaseProvider(ABC):
    """Provider 抽象基类

    所有 Provider 必须实现以下方法：
    - get_provider_name(): 返回 Provider 名称
    - chat(): 发送聊天请求
    - validate_connection(): 验证连接

    Provider 可以选择性重写：
    - get_default_model(): 返回默认模型
    - get_system_prompt(): 返回系统提示词
    """

    # 注册表：存储所有 Provider 类
    _registry: Dict[str, type] = {}

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        models: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """初始化 Provider

        Args:
            api_key: API 密钥
            api_base: API 基础 URL
            models: 模型映射字典
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.api_base = api_base
        self.models = models or {}
        self.config = kwargs

    @classmethod
    def register(cls, provider_class: type) -> type:
        """注册 Provider 类"""
        # 获取 provider_name，使用 instance 或 class 属性
        provider_name = None

        # 先尝试作为实例方法获取（通过临时实例）
        if hasattr(provider_class, 'get_provider_name'):
            try:
                # 创建临时实例
                temp_instance = provider_class(api_key="")
                provider_name = temp_instance.get_provider_name()
            except Exception:
                pass

        # 如果失败，尝试作为类方法/属性获取
        if not provider_name:
            if hasattr(provider_class, 'get_provider_name'):
                # 如果是类方法
                try:
                    provider_name = provider_class.get_provider_name()
                except TypeError:
                    # 可能是 instance method，需要实例化
                    pass
            if hasattr(provider_class, 'provider_name'):
                provider_name = getattr(provider_class, 'provider_name')

        if provider_name:
            cls._registry[provider_name] = provider_class
            logger.debug(f"Registered provider: {provider_name}")

        return provider_class

    @classmethod
    def get_registered_providers(cls) -> Dict[str, type]:
        """获取所有注册的 Provider"""
        return cls._registry.copy()

    @classmethod
    def create_provider(cls, provider_name: str, **kwargs) -> "BaseProvider":
        """创建 Provider 实例"""
        if provider_name not in cls._registry:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[provider_name](**kwargs)

    @abstractmethod
    def get_provider_name(self) -> str:
        """返回 Provider 名称

        Returns:
            Provider 名称，如 'openai', 'anthropic', 'azure', 'local'
        """
        pass

    @abstractmethod
    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """发送聊天请求

        Args:
            model: 模型名称
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            **kwargs: 其他参数如 temperature, max_tokens

        Returns:
            生成的文本内容

        Raises:
            ProviderError: Provider 调用失败
        """
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """验证连接是否可用

        Returns:
            True 如果连接正常，False 否则
        """
        pass

    def get_default_model(self, task: str = "default") -> Optional[str]:
        """获取指定任务的默认模型

        Args:
            task: 任务名称

        Returns:
            模型名称
        """
        return self.models.get(task)

    async def achat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """异步版本的 chat

        默认实现使用线程池，如果 Provider 支持异步应该重写
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.chat(model, messages, **kwargs)
        )

    def get_system_prompt(self) -> str:
        """获取系统提示词（可选重写）"""
        return ""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.get_provider_name()}>"


class ProviderError(Exception):
    """Provider 调用异常"""
    pass


class ProviderConnectionError(ProviderError):
    """Provider 连接失败"""
    pass


class ProviderRateLimitError(ProviderError):
    """Provider 限流"""
    pass


class ProviderAuthenticationError(ProviderError):
    """Provider 认证失败"""
    pass
