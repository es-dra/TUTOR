"""Minimax Provider

支持 Minimax 海螺AI API
"""

import logging
from typing import List, Dict, Any, Optional

from .base import BaseProvider, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


@BaseProvider.register
class MinimaxProvider(BaseProvider):
    """Minimax 海螺AI Provider

    API: https://api.minimax.chat
    """

    DEFAULT_API_BASE = "https://api.minimax.chat/v1"
    DEFAULT_MODELS = {
        "default": "MiniMax-01",
        "chat": "MiniMax-01",
        "embedding": "embo-01",
        "vision": "MiniMax-VL-01",
    }
    provider_name = "minimax"  # 类属性用于注册

    def __init__(
        self,
        api_key: str = "",
        api_base: Optional[str] = None,
        models: Optional[Dict[str, str]] = None,
        group_id: str = "",
        **kwargs
    ):
        """初始化 Minimax Provider

        Args:
            api_key: Minimax API Key
            api_base: API Base URL
            models: 模型映射
            group_id: Minimax Group ID (用于 API 调用)
        """
        super().__init__(
            api_key=api_key,
            api_base=api_base or self.DEFAULT_API_BASE,
            models=models or self.DEFAULT_MODELS.copy(),
            **kwargs
        )
        self.group_id = group_id or kwargs.get("group_id", "")

    def get_provider_name(self) -> str:
        return "minimax"

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """发送聊天请求到 Minimax API"""
        import httpx

        # 获取实际模型名
        actual_model = self.models.get(model, model)
        if actual_model == "MiniMax-01" and "MiniMax-01" in self.DEFAULT_MODELS.values():
            actual_model = "MiniMax-01"  # 最新模型

        # 构建请求
        url = f"{self.api_base}/text/chatcompletion_v2"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        request_body = {
            "model": actual_model,
            "messages": messages,
        }

        # 添加可选参数
        if temperature := kwargs.get("temperature"):
            request_body["temperature"] = temperature
        if max_tokens := kwargs.get("max_tokens"):
            request_body["tokens_to_generate"] = max_tokens
        if top_p := kwargs.get("top_p"):
            request_body["top_p"] = top_p

        # Minimax 特定参数
        if self.group_id:
            request_body["group_id"] = self.group_id

        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(url, json=request_body, headers=headers)
                response.raise_for_status()
                data = response.json()

            # 解析响应
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["messages"][-1]["text"]

            # 兼容不同响应格式
            if "output" in data:
                return data["output"]
            if "text" in data:
                return data["text"]

            logger.warning(f"Unexpected Minimax response format: {data}")
            return str(data)

        except httpx.HTTPStatusError as e:
            logger.error(f"Minimax API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Minimax request failed: {e}")
            raise

    def validate_connection(self) -> bool:
        """验证 Minimax API 连接"""
        import httpx

        try:
            # 尝试一个简单的模型列表请求
            url = f"{self.api_base}/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}

            with httpx.Client(timeout=10) as client:
                response = client.get(url, headers=headers)

            return response.status_code == 200

        except Exception as e:
            logger.warning(f"Minimax connection validation failed: {e}")
            return False

    def get_default_model(self, task: str = "default") -> Optional[str]:
        """获取 Minimax 默认模型"""
        return self.models.get(task) or "MiniMax-01"
