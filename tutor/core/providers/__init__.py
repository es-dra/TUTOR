"""Model Provider Module - 多模型提供商支持

提供统一的 Provider 抽象接口，支持多种模型调用方式：
- OpenAI
- DeepSeek
- Anthropic
- Azure OpenAI
- Local (Ollama / LM Studio)
- Minimax
"""

from .base import BaseProvider, ProviderConfig, ChatMessage, ChatResponse
from .openai import OpenAIProvider
from .deepseek import DeepSeekProvider
from .anthropic import AnthropicProvider
from .azure import AzureProvider
from .local import LocalProvider
from .minimax import MinimaxProvider
from .router import ProviderRouter, RouterConfig

__all__ = [
    "BaseProvider",
    "ProviderConfig",
    "ChatMessage",
    "ChatResponse",
    "OpenAIProvider",
    "DeepSeekProvider",
    "AnthropicProvider",
    "AzureProvider",
    "LocalProvider",
    "MinimaxProvider",
    "ProviderRouter",
    "RouterConfig",
]
