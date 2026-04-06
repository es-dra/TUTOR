"""
TUTOR v3 - 角色编排器
管理多角色的实时对话和协作
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable, Set
from concurrent.futures import ThreadPoolExecutor

from tutor.core.project.v3_project import (
    Project,
    RoleMessage,
    MessageType,
    DEFAULT_ROLES,
    get_role_by_id,
    ResearchRole
)
from tutor.core.model import ModelGateway

logger = logging.getLogger(__name__)


class RoleOrchestrator:
    """角色编排器 - 管理多角色对话流程"""
    
    def __init__(
        self,
        project: Project,
        model_gateway: ModelGateway,
        on_message_callback: Optional[Callable[[RoleMessage], None]] = None
    ):
        self.project = project
        self.model_gateway = model_gateway
        self.on_message_callback = on_message_callback
        self._is_running = False
        self._executor = ThreadPoolExecutor(max_workers=3)
        
    async def start_debate(self, topic: str, max_rounds: int = 3) -> List[RoleMessage]:
        """启动多角色辩论（异步版本，支持并行化角色发言）"""
        self._is_running = True
        messages: List[RoleMessage] = []
        
        try:
            # 第一轮：所有角色并行发言
            if self._is_running:
                logger.info("Starting debate round 1 - parallel role发言")
                
                # 并行生成所有角色的消息
                role_messages = await asyncio.gather(
                    *[self._generate_role_message_async(role, topic, messages, 1) for role in DEFAULT_ROLES]
                )
                
                # 处理生成的消息
                for message in role_messages:
                    if message and self._is_running:
                        messages.append(message)
                        self._broadcast_message(message)
            
            # 后续轮次：角色之间互动
            for round_num in range(2, max_rounds + 1):
                if not self._is_running:
                    break
                    
                logger.info(f"Debate round {round_num}")
                
                # 质疑者和实践者并行回应
                interactive_roles = [get_role_by_id(role_id) for role_id in ["skeptic", "pragmatist"]]
                interactive_roles = [role for role in interactive_roles if role]
                
                if interactive_roles:
                    role_messages = await asyncio.gather(
                        *[self._generate_role_message_async(role, topic, messages, round_num) for role in interactive_roles]
                    )
                    
                    for message in role_messages:
                        if message and self._is_running:
                            messages.append(message)
                            self._broadcast_message(message)
            
            # 综合者总结
            if self._is_running:
                synthesizer = get_role_by_id("synthesizer")
                if synthesizer:
                    self._broadcast_thinking(synthesizer.id)
                    summary = await self._generate_role_message_async(
                        synthesizer,
                        topic,
                        messages,
                        max_rounds + 1,
                        is_summary=True
                    )
                    if summary:
                        messages.append(summary)
                        self._broadcast_message(summary)
        
        finally:
            self._is_running = False
        
        return messages
    
    def start_debate_sync(self, topic: str, max_rounds: int = 3) -> List[RoleMessage]:
        """启动多角色辩论（同步版本，保持向后兼容）"""
        import asyncio
        return asyncio.run(self.start_debate(topic, max_rounds))
    
    def _generate_role_message(
        self,
        role: ResearchRole,
        topic: str,
        context: List[RoleMessage],
        round_num: int,
        is_summary: bool = False
    ) -> Optional[RoleMessage]:
        """生成单个角色的消息（同步版本）"""
        try:
            # 构建上下文
            context_text = self._build_context(context)
            
            prompt = self._build_prompt(role, topic, context_text, is_summary)
            
            logger.debug(f"Generating message for {role.name}")
            
            response = self.model_gateway.chat(
                role.id,
                [{"role": "user", "content": prompt}],
                temperature=0.7 if role.id == "innovator" else 0.3,
                max_tokens=500
            )
            
            if response:
                message = RoleMessage(
                    project_id=self.project.id,
                    role_id=role.id,
                    content=response.strip(),
                    message_type=MessageType.SPEAK if not is_summary else MessageType.PROPOSE,
                    metadata={
                        "round": round_num,
                        "role_color": role.color,
                        "role_emoji": role.emoji
                    }
                )
                return message
            
        except Exception as e:
            logger.error(f"Failed to generate message for {role.name}: {e}")
        
        return None
    
    async def _generate_role_message_async(
        self,
        role: ResearchRole,
        topic: str,
        context: List[RoleMessage],
        round_num: int,
        is_summary: bool = False
    ) -> Optional[RoleMessage]:
        """生成单个角色的消息（异步版本，支持并行处理）"""
        try:
            # 构建上下文
            context_text = self._build_context(context)
            
            # 构建结构化输出的提示词
            prompt = self._build_structured_prompt(role, topic, context_text, is_summary)
            
            logger.debug(f"Generating message for {role.name}")
            
            # 异步生成响应
            response = await self._async_chat(
                role.id,
                [{"role": "user", "content": prompt}],
                temperature=0.7 if role.id == "innovator" else 0.3,
                max_tokens=800
            )
            
            if response:
                # 解析结构化输出
                structured_content = self._parse_structured_response(response)
                
                # 构建消息内容
                if structured_content:
                    content = self._format_structured_content(structured_content, role)
                else:
                    content = response.strip()
                
                message = RoleMessage(
                    project_id=self.project.id,
                    role_id=role.id,
                    content=content,
                    message_type=MessageType.SPEAK if not is_summary else MessageType.PROPOSE,
                    metadata={
                        "round": round_num,
                        "role_color": role.color,
                        "role_emoji": role.emoji,
                        "structured_content": structured_content
                    }
                )
                return message
            
        except Exception as e:
            logger.error(f"Failed to generate message for {role.name}: {e}")
        
        return None
    
    async def _async_chat(self, role_id: str, messages: List[Dict], temperature: float, max_tokens: int) -> Optional[str]:
        """异步调用模型聊天"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.model_gateway.chat,
            role_id,
            messages,
            temperature,
            max_tokens
        )
    
    def _build_structured_prompt(
        self,
        role: ResearchRole,
        topic: str,
        context: str,
        is_summary: bool
    ) -> str:
        """构建结构化输出的提示词"""
        if is_summary:
            return f"""你是{role.name} {role.emoji}。

你的角色定位：{role.persona}

你的目标：{role.goal}

讨论主题：{topic}

历史对话：
{context}

请基于所有角色的观点，整合出一个一致、全面的方案。
总结各方的优点，形成最终的研究提案。

请以JSON格式输出，包含以下字段：
{{
  "观点": "你的核心观点",
  "证据": ["支持观点的证据1", "证据2"],
  "建议": ["具体建议1", "建议2"]
}}
"""
        
        return f"""你是{role.name} {role.emoji}。

你的角色定位：{role.persona}

你的目标：{role.goal}

当前讨论主题：{topic}

历史对话：
{context}

请从你的角色视角出发，对当前主题发表看法。
保持专业、有建设性的语气。

请以JSON格式输出，包含以下字段：
{{
  "观点": "你的核心观点",
  "证据": ["支持观点的证据1", "证据2"],
  "质疑": ["对其他观点的质疑1", "质疑2"],
  "建议": ["具体建议1", "建议2"]
}}
"""
    
    def _parse_structured_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析结构化响应"""
        import json
        try:
            # 提取JSON部分
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx != -1 and end_idx != -1:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"Failed to parse structured response: {e}")
        return None
    
    def _format_structured_content(self, structured_content: Dict[str, Any], role: ResearchRole) -> str:
        """格式化结构化内容为可读文本"""
        parts = []
        
        if "观点" in structured_content:
            parts.append(f"**{role.name}的观点：**\n{structured_content['观点']}")
        
        if "证据" in structured_content and structured_content['证据']:
            parts.append("**支持证据：**")
            for i, evidence in enumerate(structured_content['证据'], 1):
                parts.append(f"{i}. {evidence}")
        
        if "质疑" in structured_content and structured_content['质疑']:
            parts.append("**质疑点：**")
            for i, challenge in enumerate(structured_content['质疑'], 1):
                parts.append(f"{i}. {challenge}")
        
        if "建议" in structured_content and structured_content['建议']:
            parts.append("**建议：**")
            for i, suggestion in enumerate(structured_content['建议'], 1):
                parts.append(f"{i}. {suggestion}")
        
        return "\n\n".join(parts)
    
    def _build_context(self, messages: List[RoleMessage]) -> str:
        """构建对话上下文"""
        if not messages:
            return "这是对话的开始，还没有历史消息。"
        
        context_lines = []
        for msg in messages[-8:]:  # 最近8条消息
            role = get_role_by_id(msg.role_id)
            role_name = role.name if role else msg.role_id
            context_lines.append(f"{role_name} ({msg.timestamp[:19]}):\n{msg.content}\n")
        
        return "\n".join(context_lines)
    
    def _build_prompt(
        self,
        role: ResearchRole,
        topic: str,
        context: str,
        is_summary: bool
    ) -> str:
        """构建角色提示词"""
        if is_summary:
            return f"""你是{role.name} {role.emoji}。

你的角色定位：{role.persona}

你的目标：{role.goal}

讨论主题：{topic}

历史对话：
{context}

请基于所有角色的观点，整合出一个一致、全面的方案。
总结各方的优点，形成最终的研究提案。
请用3-5段话清晰表达。"""
        
        return f"""你是{role.name} {role.emoji}。

你的角色定位：{role.persona}

你的目标：{role.goal}

当前讨论主题：{topic}

历史对话：
{context}

请从你的角色视角出发，对当前主题发表看法。
保持专业、有建设性的语气。
请用1-3段话表达。"""
    
    def _broadcast_thinking(self, role_id: str):
        """广播思考中状态"""
        if self.on_message_callback:
            role = get_role_by_id(role_id)
            if role:
                thinking_msg = RoleMessage(
                    project_id=self.project.id,
                    role_id=role_id,
                    content=f"{role.name}正在思考...",
                    message_type=MessageType.THINK,
                    metadata={
                        "role_color": role.color,
                        "role_emoji": role.emoji
                    }
                )
                self.on_message_callback(thinking_msg)
    
    def _broadcast_message(self, message: RoleMessage):
        """广播新消息"""
        # 保存到项目
        self.project.add_role_message(message)
        
        # 回调通知
        if self.on_message_callback:
            self.on_message_callback(message)
    
    def stop(self):
        """停止编排器"""
        self._is_running = False
        logger.info("Role orchestrator stopped")
    
    async def start_debate_async(
        self,
        topic: str,
        max_rounds: int = 3
    ) -> List[RoleMessage]:
        """异步启动辩论"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.start_debate,
            topic,
            max_rounds
        )


def create_role_orchestrator(
    project: Project,
    model_gateway: ModelGateway,
    on_message: Optional[Callable[[RoleMessage], None]] = None
) -> RoleOrchestrator:
    """创建角色编排器的工厂函数"""
    return RoleOrchestrator(project, model_gateway, on_message)
