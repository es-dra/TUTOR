"""Multi-Agent Base Classes

提供智能体、消息和响应类型的基础定义。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """消息角色类型"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"  # 跨智能体消息


@dataclass
class AgentMessage:
    """智能体消息

    用于智能体之间传递的信息结构。
    """
    id: str
    sender: str
    receivers: Set[str]  # 目标智能体ID，'*' 表示广播
    content: str
    role: MessageRole = MessageRole.AGENT
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    reply_to: Optional[str] = None  # 被回复的消息ID

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "receivers": list(self.receivers),
            "content": self.content,
            "role": self.role.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        data = data.copy()
        data["receivers"] = set(data["receivers"])
        data["role"] = MessageRole(data["role"])
        return cls(**data)


@dataclass
class AgentResponse:
    """智能体响应"""
    message: AgentMessage
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message.to_dict(),
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }


class Agent(ABC):
    """智能体基类

    所有智能体都应继承此类并实现 `think` 和 `act` 方法。

    属性：
        id: 智能体唯一标识
        name: 智能体名称
        description: 智能体描述
        model_gateway: 模型网关实例
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        model_gateway: Optional[Any] = None,
    ):
        self.id = agent_id
        self.name = name
        self.description = description
        self.model_gateway = model_gateway
        self._message_history: List[AgentMessage] = []
        logger.debug(f"Agent '{self.id}' initialized: {name}")

    @abstractmethod
    def think(self, message: AgentMessage, context: Dict[str, Any]) -> AgentResponse:
        """思考阶段 - 分析消息，决定响应内容

        Args:
            message: 收到的消息
            context: 共享上下文

        Returns:
            AgentResponse: 响应消息
        """
        pass

    @abstractmethod
    def act(self, response: AgentResponse, context: Dict[str, Any]) -> Optional[AgentMessage]:
        """行动阶段 - 根据响应执行动作（如发送消息）

        Args:
            response: think 阶段的响应
            context: 共享上下文

        Returns:
            可选：发送的消息（如果 act 需要发送消息）
        """
        pass

    def receive(self, message: AgentMessage) -> AgentResponse:
        """接收消息并处理

        Args:
            message: 收到的消息

        Returns:
            AgentResponse
        """
        self._message_history.append(message)
        logger.debug(f"Agent '{self.id}' received message from '{message.sender}': {message.content[:50]}...")
        return self.think(message, {})

    def get_history(self, limit: Optional[int] = None) -> List[AgentMessage]:
        """获取消息历史"""
        if limit:
            return self._message_history[-limit:]
        return self._message_history.copy()

    def clear_history(self) -> None:
        """清空消息历史"""
        self._message_history.clear()


class LLMAgent(Agent):
    """基于大语言模型的智能体

    使用 LLM 生成响应的智能体。
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        model_gateway: Optional[Any] = None,
        system_prompt: str = "",
        model_role: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        super().__init__(agent_id, name, description, model_gateway)
        self.system_prompt = system_prompt
        self.model_role = model_role
        self.temperature = temperature
        self.max_tokens = max_tokens

    def think(self, message: AgentMessage, context: Dict[str, Any]) -> AgentResponse:
        """使用 LLM 生成响应"""
        if not self.model_gateway:
            return AgentResponse(
                message=message,
                success=False,
                error="No model gateway configured",
            )

        try:
            messages = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})

            # 构建对话历史
            for hist_msg in self.get_history(limit=10):
                role = "assistant" if hist_msg.sender == self.id else "user"
                messages.append({"role": role, "content": f"[{hist_msg.sender}]: {hist_msg.content}"})

            messages.append({"role": "user", "content": f"[{message.sender}]: {message.content}"})

            response_text = self.model_gateway.chat(
                model_name=self.model_role,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # 构建响应消息
            response_msg = AgentMessage(
                id=f"{self.id}-{datetime.now(timezone.utc).timestamp()}",
                sender=self.id,
                receivers={message.sender},
                content=response_text,
                role=MessageRole.AGENT,
                reply_to=message.id,
            )

            return AgentResponse(
                message=response_msg,
                success=True,
            )

        except Exception as e:
            logger.error(f"LLMAgent '{self.id}' failed: {e}")
            return AgentResponse(
                message=message,
                success=False,
                error=str(e),
            )

    def act(self, response: AgentResponse, context: Dict[str, Any]) -> Optional[AgentMessage]:
        """行动阶段：返回响应消息"""
        if response.success:
            return response.message
        return None
