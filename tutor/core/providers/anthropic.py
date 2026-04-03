"""Anthropic Provider

支持 Claude 系列模型的 Provider。
"""

import json
import logging
from typing import List, Dict, Any, Optional

import requests
from requests.exceptions import RequestException, Timeout

from .base import BaseProvider, ProviderError

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Anthropic Claude 模型 Provider

    Anthropic API 使用与 OpenAI 不同的消息格式，
    需要进行转换。
    """

    DEFAULT_API_BASE = "https://api.anthropic.com"
    ANTHROPIC_VERSION = "2023-06-01"
    DEFAULT_MODELS = {
        "default": "claude-3-sonnet-20240229",
        "innovator": "claude-3-opus-20240229",
        "synthesizer": "claude-3-opus-20240229",
        "evaluator": "claude-3-sonnet-20240229",
        "analyzer": "claude-3-haiku-20240307",
    }

    def __init__(
        self,
        api_key: str = "",
        api_base: str = DEFAULT_API_BASE,
        models: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """初始化 Anthropic Provider

        Args:
            api_key: Anthropic API Key
            api_base: API 基础 URL
            models: 模型映射
            **kwargs: 其他参数
        """
        super().__init__(api_key=api_key, api_base=api_base, models=models, **kwargs)
        self.max_retries = kwargs.get("max_retries", 3)
        self.timeout = kwargs.get("timeout", 60)

    def get_provider_name(self) -> str:
        return "anthropic"

    def _convert_messages(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """将 OpenAI 格式消息转换为 Anthropic 格式

        Anthropic API 要求：
        - 最后一条消息必须是 user role
        - system 消息需要单独提取

        Args:
            messages: OpenAI 格式消息

        Returns:
            Anthropic API 格式的请求体
        """
        system_prompt = ""
        anthropic_messages = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                system_prompt = content
            elif role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": content
                })
            elif role == "assistant":
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content
                })

        return {
            "system": system_prompt if system_prompt else None,
            "messages": anthropic_messages
        }

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs
    ) -> str:
        """发送聊天请求

        Args:
            model: 模型名称（如 claude-3-opus-20240229）
            messages: 消息列表（OpenAI 格式）
            temperature: 温度参数
            max_tokens: 最大 token 数（Anthropic 必须指定）
            **kwargs: 其他参数

        Returns:
            生成的文本内容
        """
        # 转换为 Anthropic 格式
        converted = self._convert_messages(messages)

        # 构建请求头
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        # 构建请求体
        payload = {
            "model": model,
            **converted,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # 添加可选参数
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]
        if "top_k" in kwargs:
            payload["top_k"] = kwargs["top_k"]
        if "stop_sequences" in kwargs:
            payload["stop_sequences"] = kwargs["stop_sequences"]

        endpoint = f"{self.api_base.rstrip('/')}/v1/messages"

        logger.info(f"Anthropic API request: model={model}")
        logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)[:500]}")

        # 发送请求
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )

                # 处理状态码
                if response.status_code == 429:
                    raise ProviderError("Rate limit exceeded (429)")
                if response.status_code == 401:
                    raise ProviderError("Authentication failed (401)")
                if response.status_code >= 500:
                    raise ProviderError(f"Server error: {response.status_code}")

                response.raise_for_status()
                result = response.json()

                # Anthropic 响应格式
                content = result["content"][0]["text"]
                logger.info(f"Anthropic API response: {len(content)} chars")

                return content

            except Timeout:
                last_error = ProviderError(f"Timeout calling {model}")
                logger.warning(f"Attempt {attempt + 1} timeout")
            except RequestException as e:
                last_error = ProviderError(f"Request failed: {e}")
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

            # 指数退避
            if attempt < self.max_retries - 1:
                import time
                delay = 2 ** attempt
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)

        raise last_error or ProviderError("All retries exhausted")

    def validate_connection(self) -> bool:
        """验证 Anthropic API 连接

        Returns:
            True 如果连接正常
        """
        if not self.api_key:
            logger.warning("Cannot validate: no API key")
            return False

        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": self.ANTHROPIC_VERSION,
            }
            response = requests.get(
                f"{self.api_base.rstrip('/')}/v1/models",
                headers=headers,
                timeout=10
            )
            # Anthropic 没有 models 端点，用简单的 health check
            return response.status_code in (200, 404)
        except Exception as e:
            logger.warning(f"Anthropic connection validation failed: {e}")
            return False

    def get_default_model(self, task: str = "default") -> Optional[str]:
        """获取默认模型"""
        return self.models.get(task) or self.DEFAULT_MODELS.get(task)
