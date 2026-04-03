"""Azure OpenAI Provider

支持 Azure OpenAI 服务的 Provider。
"""

import json
import logging
from typing import List, Dict, Any, Optional

import requests
from requests.exceptions import RequestException, Timeout

from .base import BaseProvider, ProviderError

logger = logging.getLogger(__name__)


class AzureProvider(BaseProvider):
    """Azure OpenAI 模型 Provider

    Azure OpenAI 与 OpenAI API 略有不同：
    - 使用 deployment_name 而非 model ID
    - API 版本在 URL 中
    - 不同的认证方式
    """

    DEFAULT_API_VERSION = "2024-02-01"

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        deployment_name: str = "",
        api_version: str = DEFAULT_API_VERSION,
        models: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """初始化 Azure Provider

        Args:
            api_key: Azure API Key
            api_base: Azure OpenAI 端点（如 https://xxx.openai.azure.com）
            deployment_name: Deployment 名称
            api_version: API 版本
            models: 模型映射
            **kwargs: 其他参数
        """
        super().__init__(api_key=api_key, api_base=api_base, models=models, **kwargs)
        self.deployment_name = deployment_name
        self.api_version = api_version
        self.max_retries = kwargs.get("max_retries", 3)
        self.timeout = kwargs.get("timeout", 60)

    def get_provider_name(self) -> str:
        return "azure"

    def _get_endpoint(self, path: str = "/chat/completions") -> str:
        """构建 Azure API 端点

        Args:
            path: API 路径

        Returns:
            完整的端点 URL
        """
        base = self.api_base.rstrip("/")
        deployment = self.deployment_name
        version = self.api_version
        return f"{base}/openai/deployments/{deployment}{path}?api-version={version}"

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
            model: 模型名称（Azure 中会忽略，使用 deployment_name）
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            生成的文本内容
        """
        # 构建请求头
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        # 构建请求体（Azure 使用 deployment 而非 model）
        payload = {
            "deployment": self.deployment_name,
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

        endpoint = self._get_endpoint()

        logger.info(f"Azure API request: deployment={self.deployment_name}")
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
                logger.info(f"Azure API response: {len(content)} chars")

                return content

            except Timeout:
                last_error = ProviderError(f"Timeout calling {self.deployment_name}")
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
        """验证 Azure OpenAI 连接

        Returns:
            True 如果连接正常
        """
        if not self.api_key or not self.api_base:
            logger.warning("Cannot validate: missing API key or base URL")
            return False

        try:
            headers = {"api-key": self.api_key}
            # Azure 模型列表端点
            endpoint = f"{self.api_base.rstrip('/')}/openai/models?api-version={self.api_version}"
            response = requests.get(endpoint, headers=headers, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Azure connection validation failed: {e}")
            return False
