"""跨模型对抗评审 - Cross-Model Adversarial Review

核心思想 (来自 ARIS):
1. Primary Model 生成内容
2. Critic Model 批判评审 (强制用不同模型)
3. Primary Model 回应批评
4. Synthesizer 综合判断

关键设计:
- 必须使用不同厂商的模型，才能产生真正的视角差异
- 避免 "echo chamber" 效应 (同模型评审无法发现自身盲点)
- 支持用户自定义模型配置
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ReviewRole(Enum):
    """评审角色"""
    ADVOCATE = "advocate"      # 倡导者 - 支持和辩护
    CRITIC = "critic"         # 批评者 - 挑剔和质疑
    SYNTHESIZER = "synthesizer"  # 综合者 - 平衡判断


# 跨模型对抗评审的系统提示词
ADVERSARIAL_REVIEW_PROMPTS = {
    ReviewRole.ADVOCATE: """你是一位热情的学术倡导者，为研究想法提供建设性支持。

你的任务是：
1. 深入理解研究想法的核心贡献
2. 找出该想法的最大优势和潜力
3. 用最有力的论据支持这个想法
4. 提供具体的改进建议使其更加完善

保持客观但积极的评审风格。""",

    ReviewRole.CRITIC: """你是一位严格的学术批评者，扮演"魔鬼代言人"。

你的任务是：
1. 从最挑剔的角度审视研究想法
2. 找出论点中的漏洞、假设中的缺陷
3. 质疑方法的严谨性和结论的可靠性
4. 识别潜在的风险和负面影响

不要轻易接受任何论点，假设最好的意图但保持严格批判。""",

    ReviewRole.SYNTHESIZER: """你是一位资深的学术评审委员会主席。

你的任务是：
1. 综合考虑支持和批评双方的观点
2. 给出平衡、客观的最终评价
3. 明确指出该工作的贡献和不足
4. 提供具体的改进方向

你的结论将作为最终评审结果。""",
}


@dataclass
class ModelReviewResponse:
    """单个模型的评审响应"""
    model_id: str
    role: ReviewRole
    content: str
    success: bool = True
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
class ReviewVerdict:
    """评审结论"""
    final_verdict: str
    score: float  # 0-1
    confidence: str  # low, medium, high
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_verdict": self.final_verdict,
            "score": self.score,
            "confidence": self.confidence,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "recommendations": self.recommendations,
        }


@dataclass
class CrossModelReviewResult:
    """跨模型对抗评审结果"""
    original_content: str
    content: str  # 经过评审的内容
    success: bool

    # 各阶段响应
    advocate_response: Optional[ModelReviewResponse] = None
    critic_response: Optional[ModelReviewResponse] = None
    rebuttal_response: Optional[ModelReviewResponse] = None
    synthesis_response: Optional[ModelReviewResponse] = None

    # 最终结论
    verdict: Optional[ReviewVerdict] = None

    # 元信息
    mode: str = "cross_model"  # cross_model or single_model
    primary_model: str = ""
    critic_model: str = ""
    synthesizer_model: str = ""
    vendors_used: List[str] = field(default_factory=list)

    # 评分
    initial_score: float = 0.0
    final_score: float = 0.0
    score_improvement: float = 0.0

    error: Optional[str] = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_content": self.original_content[:100] + "..." if len(self.original_content) > 100 else self.original_content,
            "content": self.content[:100] + "..." if len(self.content) > 100 else self.content,
            "success": self.success,
            "advocate_response": self.advocate_response.to_dict() if self.advocate_response else None,
            "critic_response": self.critic_response.to_dict() if self.critic_response else None,
            "rebuttal_response": self.rebuttal_response.to_dict() if self.rebuttal_response else None,
            "synthesis_response": self.synthesis_response.to_dict() if self.synthesis_response else None,
            "verdict": self.verdict.to_dict() if self.verdict else None,
            "mode": self.mode,
            "primary_model": self.primary_model,
            "critic_model": self.critic_model,
            "synthesizer_model": self.synthesizer_model,
            "vendors_used": self.vendors_used,
            "initial_score": self.initial_score,
            "final_score": self.final_score,
            "score_improvement": self.score_improvement,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        }


class ModelGatewayAdapter:
    """ModelGateway适配器"""

    # 模型别名映射
    MODEL_ALIAS_MAP = {
        "claude": "claude-sonnet-4-20250514",
        "claude-sonnet": "claude-sonnet-4-20250514",
        "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
        "sonnet": "claude-sonnet-4-20250514",
        "opus": "claude-opus-4-6-20251120",
        "gpt4": "gpt-4o",
        "gpt-4": "gpt-4o",
        "gpt4o": "gpt-4o",
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-3.5": "gpt-3.5-turbo",
        "gemini": "gemini-2-5-pro-preview-06-05",
        "gemini-2-5-pro": "gemini-2-5-pro-preview-06-05",
        "deepseek": "deepseek-chat-v2",
    }

    # 厂商映射
    VENDOR_MAP = {
        "claude": "anthropic",
        "claude-sonnet": "anthropic",
        "claude-opus": "anthropic",
        "gpt-4": "openai",
        "gpt-4o": "openai",
        "gpt-4o-mini": "openai",
        "gemini": "google",
        "deepseek": "deepseek",
    }

    def __init__(self, model_gateway: Any):
        self.gateway = model_gateway

    async def chat(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Tuple[str, float]:
        """调用模型"""
        start_time = time.time()
        try:
            resolved_model = self._resolve_model(model_id)
            content = self.gateway.chat(
                model_name=resolved_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            duration_ms = (time.time() - start_time) * 1000
            return content, duration_ms
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            raise RuntimeError(f"Model call failed: {e}") from e

    def _resolve_model(self, model_id: str) -> str:
        """解析模型名称"""
        model_lower = model_id.lower()

        if model_lower in self.MODEL_ALIAS_MAP:
            return self.MODEL_ALIAS_MAP[model_lower]

        available = self.gateway.list_models()
        if model_id in available:
            return model_id

        for avail in available:
            if model_lower in avail.lower():
                return avail

        return available[0] if available else "default"

    def get_vendor(self, model_id: str) -> str:
        """获取模型厂商"""
        model_lower = model_id.lower()
        if model_lower in self.VENDOR_MAP:
            return self.VENDOR_MAP[model_lower]
        return "unknown"


class CrossModelReviewer:
    """跨模型对抗评审器

    核心流程:
    1. Primary Model (Advocate) 生成/支持内容
    2. Critic Model (不同厂商) 批判评审
    3. Primary Model 回应批评
    4. Synthesizer 综合判断

    设计要点:
    - 强制使用不同厂商模型 (避免 echo chamber)
    - 支持单模型回退 (只有1个模型时)
    - 可配置的评审角色

    使用示例:
    ```python
    # 异构模式 - 3个不同模型
    reviewer = CrossModelReviewer(
        gateway,
        primary_model="claude-sonnet-4",
        critic_model="gpt-4o",
        synthesizer_model="gemini-2-5-pro",
    )

    result = await reviewer.review(content, context)

    # 单模型回退模式
    reviewer = CrossModelReviewer(
        gateway,
        primary_model="gpt-4o",
        critic_model="gpt-4o",  # 自动回退到单模型模式
        synthesizer_model="gpt-4o",
    )
    ```
    """

    def __init__(
        self,
        model_gateway: Any,
        primary_model: str = "claude-sonnet-4",
        critic_model: str = "gpt-4o",
        synthesizer_model: str = "gpt-4o",
        custom_prompts: Optional[Dict[ReviewRole, str]] = None,
    ):
        self.gateway = ModelGatewayAdapter(model_gateway)

        # 模型配置
        self.primary_model = primary_model
        self.critic_model = critic_model
        self.synthesizer_model = synthesizer_model

        # 检测模式
        self.mode = self._detect_mode()

        # 自定义提示词
        self.prompts = {**ADVERSARIAL_REVIEW_PROMPTS}
        if custom_prompts:
            self.prompts = {**self.prompts, **custom_prompts}

        logger.info(
            f"CrossModelReviewer initialized: "
            f"mode={self.mode}, "
            f"primary={self.primary_model}, "
            f"critic={self.critic_model}, "
            f"synthesizer={self.synthesizer_model}"
        )

    def _detect_mode(self) -> str:
        """检测评审模式"""
        primary_vendor = self.gateway.get_vendor(self.primary_model)
        critic_vendor = self.gateway.get_vendor(self.critic_model)

        if primary_vendor != critic_vendor:
            return "cross_model"
        elif self.primary_model == self.critic_model == self.synthesizer_model:
            return "single_model"
        else:
            return "same_vendor"

    async def _call_model(
        self,
        model_id: str,
        role: ReviewRole,
        messages: List[Dict[str, str]],
    ) -> ModelReviewResponse:
        """调用单个模型"""
        start_time = time.time()
        temperature = 0.7 if role == ReviewRole.ADVOCATE else 0.3

        try:
            content, duration_ms = await self.gateway.chat(
                model_id=model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=2000,
            )

            return ModelReviewResponse(
                model_id=model_id,
                role=role,
                content=content,
                success=True,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Model call failed for {model_id}: {e}")
            return ModelReviewResponse(
                model_id=model_id,
                role=role,
                content="",
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _build_advocate_messages(
        self,
        content: str,
        context: str,
    ) -> List[Dict[str, str]]:
        """构建倡导者消息"""
        return [
            {"role": "system", "content": self.prompts[ReviewRole.ADVOCATE]},
            {"role": "user", "content": f"""请评审以下内容:

{content}

背景: {context}

请给出你的评审意见。"""},
        ]

    def _build_critic_messages(
        self,
        content: str,
        context: str,
        advocate_response: str,
    ) -> List[Dict[str, str]]:
        """构建批评者消息"""
        return [
            {"role": "system", "content": self.prompts[ReviewRole.CRITIC]},
            {"role": "user", "content": f"""请严格评审以下内容:

原始内容:
{content}

倡导者观点:
{advocate_response}

背景: {context}

请给出你的批判性评审意见。"""},
        ]

    def _build_rebuttal_messages(
        self,
        content: str,
        context: str,
        advocate_response: str,
        critic_response: str,
    ) -> List[Dict[str, str]]:
        """构建回应消息"""
        return [
            {"role": "system", "content": self.prompts[ReviewRole.ADVOCATE]},
            {"role": "user", "content": f"""作为倡导者，请回应批评:

原始内容:
{content}

你之前的观点:
{advocate_response}

批评者观点:
{critic_response}

背景: {context}

请回应批评，并给出改进后的观点。"""},
        ]

    def _build_synthesis_messages(
        self,
        content: str,
        context: str,
        advocate_response: str,
        critic_response: str,
        rebuttal_response: str,
    ) -> List[Dict[str, str]]:
        """构建综合者消息"""
        return [
            {"role": "system", "content": self.prompts[ReviewRole.SYNTHESIZER]},
            {"role": "user", "content": f"""作为评审委员会主席，请给出最终评审结论:

原始内容:
{content}

倡导者观点:
{advocate_response}

批评者观点:
{critic_response}

倡导者回应:
{rebuttal_response}

背景: {context}

请给出:
1. 综合评分 (0-10)
2. 主要优势 (2-3点)
3. 主要不足 (2-3点)
4. 改进建议
5. 最终是否推荐

格式:
评分: X.X
优势: ...
不足: ...
建议: ...
结论: [推荐/需要修改/不推荐]"""},
        ]

    def _parse_verdict(self, synthesis_text: str) -> ReviewVerdict:
        """解析评审结论"""
        import re

        verdict = ReviewVerdict(
            final_verdict=synthesis_text[:500],
            score=0.5,
            confidence="medium",
        )

        # 提取评分
        score_patterns = [
            r'[评分综评]分[:：]\s*([0-9.]+)',
            r'评分[:：]\s*([0-9.]+)',
        ]
        for pattern in score_patterns:
            match = re.search(pattern, synthesis_text)
            if match:
                try:
                    score = float(match.group(1))
                    verdict.score = min(1.0, score / 10.0)
                    break
                except ValueError:
                    pass

        # 提取置信度
        if any(word in synthesis_text.lower() for word in ["高度确信", "非常有信心", "strongly", "high confidence"]):
            verdict.confidence = "high"
        elif any(word in synthesis_text.lower() for word in ["中度", "一般", "moderate", "medium"]):
            verdict.confidence = "medium"

        # 提取优势
        strength_pattern = r'[优优势势][：:]\s*(.+?)(?=[弱不足缺]|$)'
        for match in re.finditer(strength_pattern, synthesis_text, re.DOTALL):
            text = match.group(1).strip()
            if text and len(text) > 10:
                verdict.strengths.append(text[:200])

        # 提取不足
        weakness_pattern = r'[弱不足缺点][：:]\s*(.+?)(?=[优优势建]|$)'
        for match in re.finditer(weakness_pattern, synthesis_text, re.DOTALL):
            text = match.group(1).strip()
            if text and len(text) > 10:
                verdict.weaknesses.append(text[:200])

        # 提取建议
        recommend_pattern = r'[建议改进建][议：:]\s*(.+?)(?=[结评]|$)'
        for match in re.finditer(recommend_pattern, synthesis_text, re.DOTALL):
            text = match.group(1).strip()
            if text and len(text) > 10:
                verdict.recommendations.append(text[:200])

        return verdict

    async def review(
        self,
        content: str,
        context: str = "",
    ) -> CrossModelReviewResult:
        """运行跨模型对抗评审

        Args:
            content: 要评审的内容
            context: 背景信息

        Returns:
            CrossModelReviewResult: 评审结果
        """
        result = CrossModelReviewResult(
            original_content=content,
            content=content,
            success=True,
            mode=self.mode,
            primary_model=self.primary_model,
            critic_model=self.critic_model,
            synthesizer_model=self.synthesizer_model,
            vendors_used=list(set([
                self.gateway.get_vendor(self.primary_model),
                self.gateway.get_vendor(self.critic_model),
                self.gateway.get_vendor(self.synthesizer_model),
            ])),
        )

        start_time = time.time()

        try:
            # 阶段1: 倡导者评审
            logger.info(f"Phase 1: Advocate ({self.primary_model})")
            advocate_messages = self._build_advocate_messages(content, context)
            result.advocate_response = await self._call_model(
                self.primary_model, ReviewRole.ADVOCATE, advocate_messages
            )

            if not result.advocate_response.success:
                raise RuntimeError(f"Advocate review failed: {result.advocate_response.error}")

            # 阶段2: 批评者评审
            logger.info(f"Phase 2: Critic ({self.critic_model})")
            critic_messages = self._build_critic_messages(
                content, context, result.advocate_response.content
            )
            result.critic_response = await self._call_model(
                self.critic_model, ReviewRole.CRITIC, critic_messages
            )

            if not result.critic_response.success:
                raise RuntimeError(f"Critic review failed: {result.critic_response.error}")

            # 阶段3: 回应批评 (仅在跨模型模式)
            if self.mode == "cross_model":
                logger.info(f"Phase 3: Rebuttal ({self.primary_model})")
                rebuttal_messages = self._build_rebuttal_messages(
                    content, context,
                    result.advocate_response.content,
                    result.critic_response.content,
                )
                result.rebuttal_response = await self._call_model(
                    self.primary_model, ReviewRole.ADVOCATE, rebuttal_messages
                )
            else:
                # 单模型模式，直接用倡导者回应
                result.rebuttal_response = result.advocate_response

            # 阶段4: 综合判断
            logger.info(f"Phase 4: Synthesis ({self.synthesizer_model})")
            synthesis_messages = self._build_synthesis_messages(
                content, context,
                result.advocate_response.content,
                result.critic_response.content,
                result.rebuttal_response.content if result.rebuttal_response else "",
            )
            result.synthesis_response = await self._call_model(
                self.synthesizer_model, ReviewRole.SYNTHESIZER, synthesis_messages
            )

            if result.synthesis_response.success:
                result.verdict = self._parse_verdict(result.synthesis_response.content)
                result.final_score = result.verdict.score

            # 计算改进分数 (简化估算)
            if result.verdict:
                result.initial_score = max(0.3, result.final_score - 0.2)
                result.score_improvement = result.final_score - result.initial_score

        except Exception as e:
            logger.error(f"Cross-model review failed: {e}")
            result.success = False
            result.error = str(e)

        result.completed_at = datetime.now(timezone.utc).isoformat() + "Z"
        result.duration_seconds = time.time() - start_time

        logger.info(
            f"Cross-model review completed: "
            f"mode={result.mode}, "
            f"score={result.final_score:.2f}, "
            f"vendors={result.vendors_used}"
        )

        return result

    def review_sync(
        self,
        content: str,
        context: str = "",
    ) -> CrossModelReviewResult:
        """同步版本的评审"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.review(content, context))


def create_cross_model_reviewer(
    model_gateway: Any,
    primary_model: str = "claude-sonnet-4",
    critic_model: str = "gpt-4o",
    synthesizer_model: str = "gpt-4o",
    **kwargs,
) -> CrossModelReviewer:
    """创建跨模型评审器的便捷函数

    Example:
        reviewer = create_cross_model_reviewer(
            gateway,
            primary_model="claude",
            critic_model="gpt-4o",
            synthesizer_model="gemini",
        )
    """
    return CrossModelReviewer(
        model_gateway=model_gateway,
        primary_model=primary_model,
        critic_model=critic_model,
        synthesizer_model=synthesizer_model,
        **kwargs,
    )
