"""Message Bus for Agent Communication

智能体消息总线，负责消息路由和分发。
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from tutor.core.multiagent.base import Agent, AgentMessage, AgentResponse

logger = logging.getLogger(__name__)


class MessageBus:
    """智能体消息总线

    管理智能体注册、消息路由和订阅。
    支持：
    - 点对点消息
    - 广播消息
    - 订阅/发布模式
    """

    def __init__(self):
        self._agents: Dict[str, Agent] = {}
        self._subscriptions: Dict[str, List[str]] = defaultdict(list)  # topic -> [agent_id]
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._message_log: List[AgentMessage] = []

    def register(self, agent: Agent) -> None:
        """注册智能体

        Args:
            agent: 要注册的智能体实例
        """
        if agent.id in self._agents:
            logger.warning(f"Agent '{agent.id}' already registered, replacing")
        self._agents[agent.id] = agent
        logger.info(f"Agent registered: {agent.id} ({agent.name})")

    def unregister(self, agent_id: str) -> None:
        """注销智能体"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            # 清理订阅
            for topic, agents in self._subscriptions.items():
                if agent_id in agents:
                    agents.remove(agent_id)
            logger.info(f"Agent unregistered: {agent_id}")

    def subscribe(self, agent_id: str, topic: str) -> None:
        """订阅主题

        Args:
            agent_id: 智能体ID
            topic: 主题名称
        """
        if agent_id not in self._agents:
            raise ValueError(f"Unknown agent: {agent_id}")
        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
        if agent_id not in self._subscriptions[topic]:
            self._subscriptions[topic].append(agent_id)
            logger.debug(f"Agent '{agent_id}' subscribed to topic '{topic}'")

    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """取消订阅主题"""
        if topic in self._subscriptions and agent_id in self._subscriptions[topic]:
            self._subscriptions[topic].remove(agent_id)
            logger.debug(f"Agent '{agent_id}' unsubscribed from topic '{topic}'")

    def route(self, message: AgentMessage) -> List[AgentResponse]:
        """路由消息到目标智能体

        Args:
            message: 要路由的消息

        Returns:
            所有接收智能体的响应列表
        """
        self._message_log.append(message)
        responses = []

        if message.receivers == {"*"}:
            # 广播到所有已注册智能体
            target_ids = [aid for aid in self._agents.keys() if aid != message.sender]
        else:
            # 点对点或组播
            target_ids = [rid for rid in message.receivers if rid in self._agents]

        if not target_ids:
            logger.warning(f"No valid recipients for message from '{message.sender}'")
            return responses

        for target_id in target_ids:
            agent = self._agents[target_id]
            try:
                response = agent.receive(message)
                responses.append(response)
            except Exception as e:
                logger.error(f"Agent '{target_id}' failed to process message: {e}")
                responses.append(AgentResponse(
                    message=message,
                    success=False,
                    error=str(e),
                ))

        return responses

    async def publish(self, message: AgentMessage) -> List[AgentResponse]:
        """异步发布消息

        Args:
            message: 要发布的消息

        Returns:
            所有接收智能体的响应列表
        """
        return self.route(message)

    def publish_sync(self, message: AgentMessage) -> List[AgentResponse]:
        """同步发布消息（线程安全）"""
        return self.route(message)

    async def broadcast(
        self,
        sender_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[AgentResponse]:
        """广播消息到所有智能体

        Args:
            sender_id: 发送者ID
            content: 消息内容
            metadata: 元数据

        Returns:
            所有接收智能体的响应列表
        """
        message = AgentMessage(
            id=f"broadcast-{datetime.now(timezone.utc).timestamp()}",
            sender=sender_id,
            receivers={"*"},
            content=content,
            metadata=metadata or {},
        )
        return await self.publish(message)

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """获取智能体实例"""
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, str]]:
        """列出所有已注册智能体"""
        return [
            {"id": agent.id, "name": agent.name, "description": agent.description}
            for agent in self._agents.values()
        ]

    def get_message_history(
        self,
        limit: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> List[AgentMessage]:
        """获取消息历史

        Args:
            limit: 返回最近N条消息
            agent_id: 只返回涉及指定智能体的消息
        """
        history = self._message_log
        if agent_id:
            history = [
                m for m in history
                if m.sender == agent_id or agent_id in m.receivers or "*" in m.receivers
            ]
        if limit:
            return history[-limit:]
        return history.copy()

    def clear_history(self) -> None:
        """清空消息历史"""
        self._message_log.clear()
