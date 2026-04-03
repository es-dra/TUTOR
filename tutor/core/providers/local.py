"""Local Provider

支持本地模型服务（Ollama, LM Studio 等）的 Provider。
这些服务通常兼容 OpenAI API 格式。
"""

import json
import logging
from typing import List, Dict, Any, Optional

import requests
from requests.exceptions import RequestException, Timeout

from .base import BaseProvider, ProviderError

logger = logging.getLogger(__name__)


class LocalProvider(BaseProvider):
    """本地模型 Provider

    支持兼容 OpenAI API 格式的本地模型服务：
    - Ollama (http://localhost:11434/v1)
    - LM Studio (http://localhost:1234/v1)
    - LocalAI
    - 其他兼容 OpenAI API 的本地服务
    """

    DEFAULT_API_BASE = "http://localhost:11434/v1"
    DEFAULT_MODELS = {
        "default": "llama2",
        "innovator": "llama2",
        "synthesizer": "llama2",
        "evaluator": "llama2",
        "analyzer": "llama2",
    }

    def __init__(
        self,
        api_key: str = "",  # 本地服务通常不需要 API key
        api_base: str = DEFAULT_API_BASE,
        models: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """初始化 Local Provider

        Args:
            api_key: API Key（可选，本地服务通常为空）
            api_base: API 基础 URL
            models: 模型映射
            **kwargs: 其他参数
        """
        super().__init__(api_key=api_key, api_base=api_base, models=models, **kwargs)
        self.max_retries = kwargs.get("max_retries", 3)
        self.timeout = kwargs.get("timeout", 300)  # 本地模型可能需要更长时间

    def get_provider_name(self) -> str:
        return "local"

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
            model: 模型名称（如 llama2, codellama）
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            生成的文本内容
        """
        # 构建请求头
        headers = {
            "Content-Type": "application/json",
        }

        # 本地服务可能需要 API key
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

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

        logger.info(f"Local API request: model={model}, endpoint={endpoint}")
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

                content = result["choices"][0]["message"]["content"]
                logger.info(f"Local API response: {len(content)} chars")

                return content

            except Timeout:
                last_error = ProviderError(f"Timeout calling {model}")
                logger.warning(f"Attempt {attempt + 1} timeout")
            except RequestException as e:
                last_error = ProviderError(f"Request failed: {e}")
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

            # 指数退避（本地服务通常更快重试）
            if attempt < self.max_retries - 1:
                import time
                delay = 1 ** attempt
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)

        raise last_error or ProviderError("All retries exhausted")

    def validate_connection(self) -> bool:
        """验证本地服务连接

        Returns:
            True 如果连接正常
        """
        try:
            endpoint = f"{self.api_base.rstrip('/')}/models"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = requests.get(endpoint, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Local connection validation failed: {e}")
            return False

    def list_models(self) -> List[str]:
        """列出本地可用的模型

        Returns:
            模型 ID 列表
        """
        try:
            endpoint = f"{self.api_base.rstrip('/')}/models"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = requests.get(endpoint, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Ollama 格式
                if "models" in data:
                    return [m["name"] for m in data.get("models", [])]
                # OpenAI 兼容格式
                if "data" in data:
                    return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning(f"Failed to list models: {e}")

        return []
