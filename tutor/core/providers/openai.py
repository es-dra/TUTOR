"""OpenAI Provider

支持 OpenAI GPT 系列模型的 Provider。
"""

import json
import logging
from typing import List, Dict, Any, Optional

import requests
from requests.exceptions import RequestException, Timeout

from .base import BaseProvider, ProviderError, ProviderConnectionError

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """OpenAI 模型 Provider

    支持 OpenAI 官方 API 以及兼容 OpenAI API 的第三方服务。
    默认 API Base: https://api.openai.com/v1
    """

    DEFAULT_API_BASE = "https://api.openai.com/v1"
    DEFAULT_MODELS = {
        "default": "gpt-3.5-turbo",
        "innovator": "gpt-4",
        "synthesizer": "gpt-4",
        "evaluator": "gpt-4",
        "analyzer": "gpt-3.5-turbo",
    }

    def __init__(
        self,
        api_key: str = "",
        api_base: str = DEFAULT_API_BASE,
        models: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """初始化 OpenAI Provider

        Args:
            api_key: OpenAI API Key
            api_base: API 基础 URL
            models: 模型映射
            **kwargs: 其他参数如 organization, max_retries
        """
        super().__init__(api_key=api_key, api_base=api_base, models=models, **kwargs)

        self.organization = kwargs.get("organization", "")
        self.max_retries = kwargs.get("max_retries", 3)
        self.timeout = kwargs.get("timeout", 60)

    def get_provider_name(self) -> str:
        return "openai"

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """发送聊天请求

        Args:
            model: 模型名称（如 gpt-4, gpt-3.5-turbo）
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他 OpenAI 参数

        Returns:
            生成的文本内容
        """
        # 构建请求头
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.organization:
            headers["OpenAI-Organization"] = self.organization

        # 构建请求体
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # 添加可选参数
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]
        if "frequency_penalty" in kwargs:
            payload["frequency_penalty"] = kwargs["frequency_penalty"]
        if "presence_penalty" in kwargs:
            payload["presence_penalty"] = kwargs["presence_penalty"]
        if "stop" in kwargs:
            payload["stop"] = kwargs["stop"]

        endpoint = f"{self.api_base.rstrip('/')}/chat/completions"

        logger.info(f"OpenAI API request: model={model}")
        logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)[:500]}")

        # 发送请求（带重试）
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

                content = result["choices"][0]["message"]["content"]
                logger.info(f"OpenAI API response: {len(content)} chars")

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
        """验证 OpenAI API 连接

        Returns:
            True 如果连接正常
        """
        if not self.api_key:
            logger.warning("Cannot validate: no API key")
            return False

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get(
                f"{self.api_base.rstrip('/')}/models",
                headers=headers,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"OpenAI connection validation failed: {e}")
            return False

    def list_models(self) -> List[str]:
        """列出可用的模型

        Returns:
            模型 ID 列表
        """
        if not self.api_key:
            return []

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get(
                f"{self.api_base.rstrip('/')}/models",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning(f"Failed to list models: {e}")

        return []
