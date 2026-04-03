"""DeepSeek Provider

支持 DeepSeek 系列模型的 Provider。
DeepSeek API 与 OpenAI API 完全兼容，使用不同的 API Base。
"""

import logging
from typing import List, Dict, Any, Optional

from .base import BaseProvider, ProviderError, ProviderConnectionError
from .openai import OpenAIProvider

logger = logging.getLogger(__name__)


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek 模型 Provider

    DeepSeek V3 和 DeepSeek Coder 等模型。
    默认 API Base: https://api.deepseek.com
    """

    DEFAULT_API_BASE = "https://api.deepseek.com"
    DEFAULT_MODELS = {
        "default": "deepseek-chat",
        "coder": "deepseek-coder",
        "vision": "deepseek-vl",
    }

    def __init__(
        self,
        api_key: str = "",
        api_base: str = DEFAULT_API_BASE,
        models: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """初始化 DeepSeek Provider

        Args:
            api_key: DeepSeek API Key
            api_base: API 基础 URL（默认使用官方接口）
            models: 模型映射
            **kwargs: 其他参数
        """
        if models is None:
            models = self.DEFAULT_MODELS.copy()
        super().__init__(api_key=api_key, api_base=api_base, models=models, **kwargs)

    def get_provider_name(self) -> str:
        return "deepseek"

    def get_default_model(self, task: str = "default") -> Optional[str]:
        """获取指定任务的默认模型"""
        # deepseek-chat 是默认对话模型
        if task == "default" and "default" not in self.models:
            return "deepseek-chat"
        return self.models.get(task) or "deepseek-chat"
