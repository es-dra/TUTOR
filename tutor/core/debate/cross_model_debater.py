"""跨模型辩论编排器 - Cross-Model Debate Orchestrator

核心功能:
1. 异构辩论模式: 每个角色使用不同模型，强制视角多样性
2. 单模型回退模式: 单模型时复用 (生成+批判由同一模型完成)
3. 交叉质询: 模型间互相评审和反驳
4. 评分聚合: 多维度评分和综合结论

设计原则:
- 2+ 模型: 真正异构辩论
- 1 模型: 自动回退到单模型辩论 (同一模型轮流扮演正反方)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .model_config import (
    DebateRole,
    DebateModelConfig,
    ModuleModelConfig,
    ModelAssignment,
    RoleModelAssignment,
    get_default_debate_config,
    MODEL_VENDOR_MAP,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    """单个模型的响应"""
    model_id: str
    role: DebateRole
    content: str
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "role": self.role.value,
            "content": self.content,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class DebateTurn:
    """单轮辩论"""
    round_number: int
    speaker_role: DebateRole
    speaker_model: str
    content: str
    target_roles: List[DebateRole] = field(default_factory=list)
    responses: List[ModelResponse] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round": self.round_number,
            "speaker_role": self.speaker_role.value,
            "speaker_model": self.speaker_model,
            "content": self.content,
            "target_roles": [r.value for r in self.target_roles],
            "responses": [r.to_dict() for r in self.responses],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateTurn":
        """从字典重建 DebateTurn 对象（用于检查点恢复）"""
        from .model_config import DebateRole
        # Handle responses
        responses = []
        for r in data.get("responses", []):
            if isinstance(r, ModelResponse):
                responses.append(r)
            elif isinstance(r, dict):
                responses.append(ModelResponse(
                    model_id=r.get("model_id", ""),
                    role=DebateRole(r.get("role", "innovator")) if isinstance(r.get("role"), str) else r.get("role", DebateRole.INNOVATOR),
                    content=r.get("content", ""),
                    success=r.get("success", False),
                    error=r.get("error"),
                    duration_ms=r.get("duration_ms", 0.0),
                    metadata=r.get("metadata", {}),
                ))

        # Handle target_roles
        target_roles = []
        for tr in data.get("target_roles", []):
            if isinstance(tr, DebateRole):
                target_roles.append(tr)
            elif isinstance(tr, str):
                target_roles.append(DebateRole(tr))

        return cls(
            round_number=data.get("round", data.get("round_number", 0)),
            speaker_role=DebateRole(data["speaker_role"]) if isinstance(data.get("speaker_role"), str) else data.get("speaker_role", DebateRole.INNOVATOR),
            speaker_model=data.get("speaker_model", ""),
            content=data.get("content", ""),
            target_roles=target_roles,
            responses=responses,
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class DebateResult:
    """辩论最终结果"""
    debate_id: str
    topic: str
    success: bool
    error: Optional[str] = None

    # 辩论过程
    turns: List[DebateTurn] = field(default_factory=list)
    total_rounds: int = 0

    # 评分
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    confidence_level: str = "low"  # low, medium, high

    # 最终结论
    final_conclusion: str = ""
    winning_position: Optional[str] = None
    key_arguments: List[str] = field(default_factory=list)
    counter_arguments: List[str] = field(default_factory=list)

    # 配置信息
    mode: str = "heterogeneous"  # heterogeneous or single_model
    models_used: List[str] = field(default_factory=list)
    vendors_used: List[str] = field(default_factory=list)

    # 元数据
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "debate_id": self.debate_id,
            "topic": self.topic[:100] + "..." if len(self.topic) > 100 else self.topic,
            "success": self.success,
            "error": self.error,
            "turns": [t.to_dict() if hasattr(t, 'to_dict') else t for t in self.turns],
            "total_rounds": self.total_rounds,
            "dimension_scores": self.dimension_scores,
            "overall_score": self.overall_score,
            "confidence_level": self.confidence_level,
            "final_conclusion": self.final_conclusion,
            "winning_position": self.winning_position,
            "key_arguments": self.key_arguments,
            "counter_arguments": self.counter_arguments,
            "mode": self.mode,
            "models_used": self.models_used,
            "vendors_used": self.vendors_used,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateResult":
        """从字典重建 DebateResult 对象（用于检查点恢复）"""
        # Handle turns - could be list of dicts or list of DebateTurn objects
        turns = []
        for t in data.get("turns", []):
            if isinstance(t, DebateTurn):
                turns.append(t)
            elif isinstance(t, dict):
                turns.append(DebateTurn.from_dict(t))

        return cls(
            debate_id=data.get("debate_id", ""),
            topic=data.get("topic", ""),
            success=data.get("success", False),
            error=data.get("error"),
            turns=turns,
            total_rounds=data.get("total_rounds", 0),
            dimension_scores=data.get("dimension_scores", {}),
            overall_score=data.get("overall_score", 0.0),
            confidence_level=data.get("confidence_level", "low"),
            final_conclusion=data.get("final_conclusion", ""),
            winning_position=data.get("winning_position"),
            key_arguments=data.get("key_arguments", []),
            counter_arguments=data.get("counter_arguments", []),
            mode=data.get("mode", "heterogeneous"),
            models_used=data.get("models_used", []),
            vendors_used=data.get("vendors_used", []),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


class ModelGatewayAdapter:
    """ModelGateway适配器

    统一不同模型的调用接口
    """

    def __init__(self, model_gateway: Any):
        self.gateway = model_gateway

    def chat(
        self,
        model: ModelAssignment,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, float]:
        """调用模型 (同步)

        Returns:
            (response_content, duration_ms)
        """
        start_time = time.time()

        temp = temperature if temperature is not None else model.temperature
        tokens = max_tokens if max_tokens is not None else model.max_tokens

        try:
            # 根据模型ID确定调用的模型名称
            # 这里做了一个映射，用户配置的model_id可能需要映射到gateway中的名称
            model_name = self._resolve_model_name(model.model_id)

            content = self.gateway.chat(
                model_name=model_name,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
            )

            duration_ms = (time.time() - start_time) * 1000
            return content, duration_ms

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            raise ModelCallError(f"Model call failed: {e}") from e

    # 模型别名到实际model_id的映射
    MODEL_ALIAS_MAP = {
        # Anthropic
        "claude": "claude-sonnet-4-20250514",
        "claude-sonnet": "claude-sonnet-4-20250514",
        "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
        "claude-3-5": "claude-3-5-sonnet-20241022",
        "claude-opus": "claude-opus-4-6-20251120",
        "sonnet": "claude-sonnet-4-20250514",
        "opus": "claude-opus-4-6-20251120",
        # OpenAI
        "gpt4": "gpt-4o",
        "gpt-4": "gpt-4o",
        "gpt4o": "gpt-4o",
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-3.5": "gpt-3.5-turbo",
        "gpt-3.5-turbo": "gpt-3.5-turbo",
        # Google
        "gemini": "gemini-2-5-pro-preview-06-05",
        "gemini-2-5-pro": "gemini-2-5-pro-preview-06-05",
        "gemini-2-5-flash": "gemini-2-5-flash-preview-06-05",
        # DeepSeek
        "deepseek": "deepseek-chat",
        "deepseek-chat": "deepseek-chat-v2",
    }

    def _resolve_model_name(self, model_id: str) -> str:
        """将用户友好的模型ID解析为gateway中的模型名称"""
        model_lower = model_id.lower()

        # 1. 检查别名映射
        if model_lower in self.MODEL_ALIAS_MAP:
            resolved = self.MODEL_ALIAS_MAP[model_lower]
            logger.debug(f"Resolved alias '{model_id}' -> '{resolved}'")
            return resolved

        # 2. 检查完整model_id
        available = self.gateway.list_models()
        if model_id in available:
            return model_id

        # 3. 尝试前缀匹配
        for avail in available:
            avail_lower = avail.lower()
            if model_lower in avail_lower or avail_lower in model_lower:
                logger.debug(f"Resolved prefix match '{model_id}' -> '{avail}'")
                return avail

        # 4. 检查模型厂商关键词匹配
        vendor_keywords = {
            "claude": ["claude", "sonnet", "opus"],
            "gpt": ["gpt-4", "gpt-4o", "gpt-3.5"],
            "gemini": ["gemini"],
            "deepseek": ["deepseek"],
        }

        for vendor, keywords in vendor_keywords.items():
            for kw in keywords:
                if kw in model_lower:
                    for avail in available:
                        if any(k in avail.lower() for k in keywords):
                            logger.debug(f"Resolved vendor '{model_id}' -> '{avail}'")
                            return avail

        # 5. 默认回退到第一个可用模型
        if available:
            logger.warning(f"Could not resolve '{model_id}', falling back to '{available[0]}'")
            return available[0]

        logger.warning(f"No models available, using 'default'")
        return "default"


class ModelCallError(Exception):
    """模型调用错误"""
    pass


class CrossModelDebater:
    """跨模型辩论编排器

    支持两种模式:
    1. 异构模式 (heterogeneous): 2+模型，每个角色独立
    2. 单模型回退模式 (single_model): 1模型，同模型轮流扮演不同角色

    使用示例:
    ```python
    # 异构模式 - 2个不同模型
    config = create_user_config("idea_debate", {
        "innovator": ["claude-sonnet-4"],
        "skeptic": ["gpt-4o"],
        "pragmatist": ["gemini-2-5-pro"],
        "expert": ["claude-sonnet-4"],
        "synthesizer": ["gpt-4o"],
    })

    debater = CrossModelDebater(model_gateway, config)
    result = await debater.debate("如何改进Transformer架构?")

    # 单模型回退模式 - 只有1个模型
    config = create_user_config("idea_debate", {
        "innovator": ["gpt-4o"],
        "skeptic": ["gpt-4o"],  # 会自动检测为单模型模式
        "synthesizer": ["gpt-4o"],
    })
    ```

    Args:
        model_gateway: ModelGateway实例
        module_config: 模块配置
        debate_id: 辩论标识符
    """

    # 角色默认系统提示词
    DEFAULT_ROLE_PROMPTS = {
        DebateRole.INNOVATOR: """你是一位富有创造力的研究者，喜欢探索新颖的想法和突破性方法。
你的目标是提出创新且有雄心的研究想法。
思考要跳出常规框架，关注根本性的创新。""",

        DebateRole.SKEPTIC: """你是一位批判性思考者，擅长挑战假设和发现潜在缺陷。
你的目标是批评想法并识别风险或弱点。
要有建设性但严格，不要轻易接受任何论点。""",

        DebateRole.PRAGMATIST: """你是一位务实的科学家，关注可行性和实现细节。
你的目标是评估可行性并提出实际改进方案。
考虑资源、时间和技术挑战。""",

        DebateRole.EXPERT: """你是一位拥有深厚领域知识的专家。
你的目标是确保想法扎根于当前研究，识别相关文献。
提供对最新技术和方法的洞察。""",

        DebateRole.SYNTHESIZER: """你是一位综合分析专家。
你的目标是从多个角度汇总论点，形成平衡的结论。
识别共识点和分歧点，给出最终建议。""",

        DebateRole.CRITIC: """你是一位对抗性评审者，扮演"魔鬼代言人"。
你的目标是从最挑剔的角度找出论点的漏洞。
假设最佳意图但不要放过任何逻辑缺陷。""",

        DebateRole.ADVOCATE: """你是一位热情的倡导者，为研究想法辩护。
你的目标是用最有力的论据支持想法。
承认合理的批评但要强调想法的价值。""",
    }

    def __init__(
        self,
        model_gateway: Any,
        module_config: Optional[ModuleModelConfig] = None,
        debate_id: Optional[str] = None,
        custom_prompts: Optional[Dict[str, str]] = None,
    ):
        self.gateway = ModelGatewayAdapter(model_gateway)
        self.config = module_config or get_default_debate_config("idea_debate")
        self.debate_id = debate_id or f"debate-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.custom_prompts = custom_prompts or {}

        # 检测运行模式
        self._detect_mode()

        logger.info(
            f"CrossModelDebater initialized: mode={self.mode}, "
            f"vendors={self.config.get_unique_vendors()}"
        )

    def _detect_mode(self) -> None:
        """检测辩论模式"""
        # 统计所有模型
        all_models: List[ModelAssignment] = []
        for assignment in self.config.role_assignments:
            all_models.extend(assignment.models)

        unique_models = set(m.model_id for m in all_models)

        if len(unique_models) >= 2:
            self.mode = "heterogeneous"
        else:
            self.mode = "single_model"

        logger.info(
            f"Detected mode: {self.mode} "
            f"(unique_models={len(unique_models)})"
        )

    def _get_role_prompt(self, role: DebateRole, context: str = "") -> str:
        """获取角色的系统提示词"""
        # 先检查自定义提示词
        if role.value in self.custom_prompts:
            return self.custom_prompts[role.value]

        # 检查角色分配中是否有自定义模板
        role_assignment = self.config.get_role(role)
        if role_assignment and role_assignment.prompt_template:
            return role_assignment.prompt_template

        # 返回默认提示词
        return self.DEFAULT_ROLE_PROMPTS.get(role, "")

    def _build_messages(
        self,
        role: DebateRole,
        topic: str,
        context: str = "",
        debate_history: Optional[List[DebateTurn]] = None,
        extra_instructions: str = "",
    ) -> List[Dict[str, str]]:
        """构建消息列表"""
        system_prompt = self._get_role_prompt(role)

        messages = [{"role": "system", "content": system_prompt}]

        # 添加上下文
        if context:
            messages.append({
                "role": "user",
                "content": f"研究背景:\n{context}\n\n"
            })

        # 添加辩论历史
        if debate_history:
            history_text = "\n\n=== 之前的辩论讨论 ===\n"
            for turn in debate_history:
                speaker_info = f"[{turn.speaker_role.value} via {turn.speaker_model}]"
                history_text += f"\n{speaker_info}:\n{turn.content}\n"

                # 添加对该轮的反应
                if turn.responses:
                    for resp in turn.responses:
                        history_text += f"  → [{resp.role.value} via {resp.model_id}]: {resp.content[:200]}...\n"

            messages.append({"role": "user", "content": history_text})

        # 添加主题
        topic_prompt = f"""研究主题/想法: {topic}

{extra_instructions}"""

        messages.append({"role": "user", "content": topic_prompt})

        return messages

    async def _call_model(
        self,
        model: ModelAssignment,
        messages: List[Dict[str, str]],
        role: DebateRole,
    ) -> ModelResponse:
        """调用单个模型"""
        try:
            content, duration_ms = self.gateway.chat(
                model=model,
                messages=messages,
            )
            return ModelResponse(
                model_id=model.model_id,
                role=role,
                content=content,
                success=True,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error(f"Model call failed for {model.model_id}: {e}")
            return ModelResponse(
                model_id=model.model_id,
                role=role,
                content="",
                success=False,
                error=str(e),
            )

    async def _run_heterogeneous_debate(
        self,
        topic: str,
        context: str = "",
        rounds: int = 2,
    ) -> DebateResult:
        """运行异构辩论 (2+模型)

        每个角色使用各自配置的模型，真正实现视角多样性
        """
        result = DebateResult(
            debate_id=self.debate_id,
            topic=topic,
            success=True,
            mode="heterogeneous",
            models_used=list(set(
                m.model_id
                for a in self.config.role_assignments
                for m in a.models
            )),
            vendors_used=self.config.get_unique_vendors(),
        )

        debate_history: List[DebateTurn] = []

        # 辩论轮次
        for round_num in range(1, rounds + 1):
            logger.info(f"Heterogeneous debate round {round_num}/{rounds}")

            for role_assignment in self.config.role_assignments:
                if not role_assignment.models:
                    continue

                role = role_assignment.role
                model = role_assignment.primary_model  # 每个角色用第一个模型

                # 确定目标角色 (其他角色)
                other_roles = [
                    ra.role for ra in self.config.role_assignments
                    if ra.role != role
                ]

                # 构建指令
                extra = ""
                if round_num == 1:
                    extra = "首次发言，请清晰阐述你的立场。"
                else:
                    extra = f"第{round_num}轮，请回应之前的讨论并进行交叉质询。"

                messages = self._build_messages(
                    role=role,
                    topic=topic,
                    context=context,
                    debate_history=debate_history if debate_history else None,
                    extra_instructions=extra,
                )

                response = await self._call_model(model, messages, role)

                turn = DebateTurn(
                    round_number=round_num,
                    speaker_role=role,
                    speaker_model=model.model_id,
                    content=response.content,
                    target_roles=other_roles,
                    responses=[],
                )

                # 如果启用交叉质询，让其他角色回应
                if self.config.enable_cross_examination:
                    cross_tasks = []
                    for target_role in other_roles[:2]:  # 限制回应数量
                        target_assignment = self.config.get_role(target_role)
                        if target_assignment and target_assignment.primary_model:
                            cross_msg = self._build_messages(
                                role=target_role,
                                topic=topic,
                                context=context,
                                debate_history=debate_history + [turn],
                                extra_instructions=f"请评价和回应 [{role.value}] 的观点。",
                            )
                            cross_tasks.append(
                                self._call_model(
                                    target_assignment.primary_model,
                                    cross_msg,
                                    target_role,
                                )
                            )

                    if cross_tasks:
                        cross_responses = await asyncio.gather(*cross_tasks)
                        turn.responses = [r for r in cross_responses if r.success]

                debate_history.append(turn)
                result.turns = debate_history

        # 综合结论
        await self._synthesize_conclusion(result, topic, context, debate_history)

        result.total_rounds = len(debate_history)
        result.completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if debate_history:
            first_turn = debate_history[0]
            start = datetime.fromisoformat(first_turn.timestamp.replace("Z", "+00:00"))
            result.duration_seconds = (datetime.now(timezone.utc) - start).total_seconds()

        return result

    async def _run_single_model_debate(
        self,
        topic: str,
        context: str = "",
        rounds: int = 2,
    ) -> DebateResult:
        """运行单模型辩论 (1模型复用)

        同一个模型轮流扮演不同角色进行辩论
        创新者和怀疑者由同一模型扮演，但使用不同的系统提示
        """
        # 获取唯一的模型
        all_models: List[ModelAssignment] = []
        for assignment in self.config.role_assignments:
            all_models.extend(assignment.models)

        if not all_models:
            return DebateResult(
                debate_id=self.debate_id,
                topic=topic,
                success=False,
                error="No models configured",
                mode="single_model",
            )

        model = all_models[0]  # 使用第一个配置的唯一模型

        result = DebateResult(
            debate_id=self.debate_id,
            topic=topic,
            success=True,
            mode="single_model",
            models_used=[model.model_id],
            vendors_used=[model.vendor],
        )

        debate_history: List[DebateTurn] = []

        # 单模型辩论: 轮流扮演不同角色
        # 定义辩论流程
        debate_sequence = [
            (DebateRole.INNOVATOR, "首次发言，请清晰阐述你的创新研究想法。"),
            (DebateRole.SKEPTIC, "作为怀疑者，请批判性地评审上述想法，找出弱点。"),
            (DebateRole.INNOVATOR, "作为创新者，为你的想法辩护，回应批评。"),
            (DebateRole.PRAGMATIST, "作为务实者，评估这个想法的可行性和实际价值。"),
            (DebateRole.SKEPTIC, "再次质疑，考虑可行性后还有什么问题？"),
            (DebateRole.SYNTHESIZER, "作为综合者，汇总这次辩论的要点，给出最终评价。"),
        ]

        for i, (role, instruction) in enumerate(debate_sequence[:rounds * 3]):
            round_num = i // 3 + 1
            sub_turn = i % 3

            logger.info(f"Single-model debate turn {i+1}: {role.value} via {model.model_id}")

            # 获取该角色的prompt
            role_assignment = self.config.get_role(role)
            if role_assignment and role_assignment.primary_model:
                # 如果该角色有配置，使用其配置的温度等
                role_model = role_assignment.primary_model
            else:
                role_model = model

            messages = self._build_messages(
                role=role,
                topic=topic,
                context=context,
                debate_history=debate_history,
                extra_instructions=instruction,
            )

            response = await self._call_model(role_model, messages, role)

            turn = DebateTurn(
                round_number=round_num,
                speaker_role=role,
                speaker_model=model.model_id,
                content=response.content,
                target_roles=[r for r, _ in debate_sequence if r != role][:2],
                responses=[],
            )

            debate_history.append(turn)
            result.turns = debate_history

        # 综合结论
        await self._synthesize_conclusion(result, topic, context, debate_history)

        result.total_rounds = len(debate_history)
        result.completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if debate_history:
            first_turn = debate_history[0]
            start = datetime.fromisoformat(first_turn.timestamp.replace("Z", "+00:00"))
            result.duration_seconds = (datetime.now(timezone.utc) - start).total_seconds()

        return result

    async def _synthesize_conclusion(
        self,
        result: DebateResult,
        topic: str,
        context: str,
        debate_history: List[DebateTurn],
    ) -> None:
        """综合辩论结论"""
        synthesizer_assignment = self.config.get_role(DebateRole.SYNTHESIZER)

        if not synthesizer_assignment:
            # 没有综合者，使用默认逻辑
            self._default_synthesize(result, debate_history)
            return

        synthesizer_model = synthesizer_assignment.primary_model
        if not synthesizer_model:
            self._default_synthesize(result, debate_history)
            return

        # 构建综合prompt
        debate_summary = "\n\n".join([
            f"[{turn.speaker_role.value}]: {turn.content[:300]}..."
            for turn in debate_history
        ])

        synthesis_prompt = f"""基于以下辩论，请给出综合评价:

主题: {topic}

背景: {context}

辩论内容:
{debate_summary}

请给出:
1. 综合评分 (0-10): 从创新性、可行性、影响力等维度
2. 关键优势 (2-3点)
3. 主要弱点 (2-3点)
4. 总体结论和建议

格式:
评分: X.X
优势: ...
弱点: ...
结论: ..."""

        messages = [
            {"role": "system", "content": self._get_role_prompt(DebateRole.SYNTHESIZER)},
            {"role": "user", "content": synthesis_prompt},
        ]

        try:
            synthesis_response, _ = self.gateway.chat(
                synthesizer_model, messages,
            )

            result.final_conclusion = synthesis_response

            # 尝试解析评分
            self._parse_synthesis_scores(result, synthesis_response)

        except Exception as e:
            logger.warning(f"Synthesis failed, using default: {e}")
            self._default_synthesize(result, debate_history)

    def _default_synthesize(
        self,
        result: DebateResult,
        debate_history: List[DebateTurn],
    ) -> None:
        """默认综合逻辑"""
        if not debate_history:
            return

        # 简单统计各角色的发言
        role_contents = {}
        for turn in debate_history:
            role = turn.speaker_role
            if role not in role_contents:
                role_contents[role] = []
            role_contents[role].append(turn.content)

        # 提取关键论点
        innovator_text = " ".join(role_contents.get(DebateRole.INNOVATOR, []))
        skeptic_text = " ".join(role_contents.get(DebateRole.SKEPTIC, []))

        result.key_arguments = [
            innovator_text[:200] + "..." if len(innovator_text) > 200 else innovator_text
        ]
        result.counter_arguments = [
            skeptic_text[:200] + "..." if len(skeptic_text) > 200 else skeptic_text
        ]

        result.overall_score = 0.5  # 默认中等评分
        result.confidence_level = "low"
        result.final_conclusion = (
            f"辩论完成，共{len(debate_history)}轮。"
            f"创新者提出了新的想法，怀疑者提出了质疑。"
            f"建议进一步评估可行性和实际价值。"
        )

    def _parse_synthesis_scores(
        self,
        result: DebateResult,
        synthesis_text: str,
    ) -> None:
        """从综合文本中解析评分"""
        import re

        # 提取评分
        score_pattern = r'[评综]分[:：]?\s*([0-9.]+)'
        match = re.search(score_pattern, synthesis_text)
        if match:
            try:
                score = float(match.group(1))
                # 转换为0-1范围
                result.overall_score = min(1.0, score / 10.0)
            except ValueError:
                pass

        # 提取置信度
        if any(word in synthesis_text for word in ["高度确信", "非常有信心", "strongly"]):
            result.confidence_level = "high"
        elif any(word in synthesis_text for word in ["中度确信", "一般", "moderate"]):
            result.confidence_level = "medium"

        # 提取关键论点
        advantage_pattern = r'[优优势势][：:]\s*(.+?)(?=[弱缺点]|$)'
        for match in re.finditer(advantage_pattern, synthesis_text, re.DOTALL):
            result.key_arguments.append(match.group(1).strip()[:200])

        disadvantage_pattern = r'[弱缺点][：:]\s*(.+?)(?=[优优势结]|$)'
        for match in re.finditer(disadvantage_pattern, synthesis_text, re.DOTALL):
            result.counter_arguments.append(match.group(1).strip()[:200])

    async def debate(
        self,
        topic: str,
        context: str = "",
        rounds: Optional[int] = None,
    ) -> DebateResult:
        """运行辩论

        Args:
            topic: 辩论主题 (研究想法/问题)
            context: 额外背景信息
            rounds: 辩论轮数 (None则使用配置中的默认值)

        Returns:
            DebateResult: 辩论结果
        """
        rounds = rounds or self.config.debate_rounds

        logger.info(
            f"Starting debate: topic='{topic[:50]}...', "
            f"mode={self.mode}, rounds={rounds}"
        )

        try:
            if self.mode == "heterogeneous":
                result = await self._run_heterogeneous_debate(topic, context, rounds)
            else:
                result = await self._run_single_model_debate(topic, context, rounds)

            result.success = True
            logger.info(
                f"Debate completed: {result.debate_id}, "
                f"score={result.overall_score:.2f}, "
                f"confidence={result.confidence_level}"
            )

            return result

        except Exception as e:
            logger.error(f"Debate failed: {e}", exc_info=True)
            return DebateResult(
                debate_id=self.debate_id,
                topic=topic,
                success=False,
                error=str(e),
                mode=self.mode,
            )

    def debate_sync(
        self,
        topic: str,
        context: str = "",
        rounds: Optional[int] = None,
    ) -> DebateResult:
        """同步版本的辩论 (用于非异步环境)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在运行中，创建一个新循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            return loop.run_until_complete(self.debate(topic, context, rounds))
        finally:
            pass  # 不要关闭loop，让它被复用


def create_cross_model_debater(
    model_gateway: Any,
    module_name: str = "idea_debate",
    role_model_map: Optional[Dict[str, List[str]]] = None,
    **kwargs,
) -> CrossModelDebater:
    """创建跨模型辩论编排器的便捷函数

    Args:
        model_gateway: ModelGateway实例
        module_name: 模块名称
        role_model_map: 角色到模型的映射
            例如: {"innovator": ["claude"], "skeptic": ["gpt-4o"]}
            注意: 只设置1个模型会自动回退到单模型模式
        **kwargs: 传递给ModuleModelConfig的额外参数

    Example:
        # 异构模式 (2个不同模型)
        debater = create_cross_model_debater(
            gateway,
            role_model_map={
                "innovator": ["claude"],
                "skeptic": ["gpt-4o"],
                "pragmatist": ["gemini"],
                "expert": ["claude"],
                "synthesizer": ["gpt-4o"],
            }
        )

        # 单模型回退模式
        debater = create_cross_model_debater(
            gateway,
            role_model_map={
                "innovator": ["gpt-4o"],
                "skeptic": ["gpt-4o"],  # 自动回退
                "synthesizer": ["gpt-4o"],
            }
        )
    """
    from .model_config import create_user_config

    if role_model_map:
        config = create_user_config(module_name, role_model_map, **kwargs)
    else:
        config = get_default_debate_config(module_name)

    return CrossModelDebater(model_gateway, config)
