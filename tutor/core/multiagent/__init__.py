"""TUTOR Multi-Agent Collaboration Framework

多智能体协作框架，支持：
- 基于角色的智能体定义
- 消息总线进行智能体间通信
- 编排器协调多智能体工作流
"""

from tutor.core.multiagent.base import Agent, AgentMessage, AgentResponse
from tutor.core.multiagent.message_bus import MessageBus
from tutor.core.multiagent.orchestrator import AgentOrchestrator

__all__ = [
    "Agent",
    "AgentMessage",
    "AgentResponse",
    "MessageBus",
    "AgentOrchestrator",
]
