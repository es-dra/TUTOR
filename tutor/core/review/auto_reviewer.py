"""自动评审循环 - Auto Review Loop

核心功能:
1. 多模型并行评审 - 同时调用多个模型进行评审
2. 评分聚合 - 汇总多模型评审意见
3. 迭代改进 - 根据评审意见修改内容
4. 收敛判断 - 达到阈值自动停止
5. 跨模型支持 - 使用不同厂商模型

类似 ARIS 的 /auto-review-loop 思想，但支持用户自定义模型配置
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 默认评审提示词
DEFAULT_REVIEW_PROMPTS = {
    "advocate": """你是一位热情的倡导者，为研究想法提供建设性的支持。
你的目标是：
1. 找出想法的优势和潜在价值
2. 提供具体的改进建议使其更好
3. 用最有力的论据支持想法

请从创新性、可行性、影响力等维度给出评价。""",

    "critic": """你是一位严格的评审者，扮演"魔鬼代言人"。
你的目标是：
1. 从最挑剔的角度找出论点的漏洞
2. 识别潜在的问题和风险
3. 提出尖锐但建设性的批评

请给出具体的反驳意见和改进方向。""",

    "reviewer": """你是一位资深的学术评审专家。
你的目标是：
1. 综合评估研究工作的质量
2. 检查方法论的严谨性
3. 评估结论的合理性
4. 提供专业的改进建议

请从学术标准给出客观评价。""",
}


@dataclass
class ReviewConfig:
    """评审配置

    Attributes:
        max_iterations: 最大迭代次数
        score_threshold: 通过阈值 (0-1)
        models: 评审使用的模型列表
        review_prompts: 自定义评审提示词
        parallel_reviews: 是否并行调用多个评审模型
        improvement_strength: 每次改进的强度 (0-1)
        require_cross_vendor: 是否强制要求跨厂商
    """
    max_iterations: int = 3
    score_threshold: float = 0.7
    models: List[str] = field(default_factory=lambda: ["gpt-4o", "claude-sonnet-4"])
    review_prompts: Dict[str, str] = field(default_factory=lambda: DEFAULT_REVIEW_PROMPTS)
    parallel_reviews: bool = True
    improvement_strength: float = 0.8
    require_cross_vendor: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewConfig":
        """从字典创建配置"""
        return cls(
            max_iterations=data.get("max_iterations", 3),
            score_threshold=data.get("score_threshold", 0.7),
            models=data.get("models", ["gpt-4o", "claude-sonnet-4"]),
            review_prompts=data.get("review_prompts", DEFAULT_REVIEW_PROMPTS),
            parallel_reviews=data.get("parallel_reviews", True),
            improvement_strength=data.get("improvement_strength", 0.8),
            require_cross_vendor=data.get("require_cross_vendor", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "score_threshold": self.score_threshold,
            "models": self.models,
            "parallel_reviews": self.parallel_reviews,
            "improvement_strength": self.improvement_strength,
            "require_cross_vendor": self.require_cross_vendor,
        }


@dataclass
class ModelReviewResponse:
    """单个模型的评审响应"""
    model_id: str
    content: str
    scores: Dict[str, float] = field(default_factory=dict)
    # 各维度评分 (0-1)
    innovation: float = 0.0
    feasibility: float = 0.0
    methodology: float = 0.0
    impact: float = 0.0
    clarity: float = 0.0
    # 综合评分
    overall_score: float = 0.0
    success: bool = True
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "content": self.content,
            "scores": self.scores,
            "innovation": self.innovation,
            "feasibility": self.feasibility,
            "methodology": self.methodology,
            "impact": self.impact,
            "clarity": self.clarity,
            "overall_score": self.overall_score,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ReviewIteration:
    """单轮评审迭代"""
    iteration: int
    content: str  # 评审前的内容
    improved_content: Optional[str] = None  # 改进后的内容
    reviews: List[ModelReviewResponse] = field(default_factory=list)
    aggregated_score: float = 0.0
    score_delta: float = 0.0  # 与上一轮的分数变化
    converged: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "content": self.content[:100] + "..." if len(self.content) > 100 else self.content,
            "improved_content": (
                self.improved_content[:100] + "..."
                if self.improved_content and len(self.improved_content) > 100
                else self.improved_content
            ),
            "reviews": [r.to_dict() for r in self.reviews],
            "aggregated_score": self.aggregated_score,
            "score_delta": self.score_delta,
            "converged": self.converged,
            "timestamp": self.timestamp,
        }


@dataclass
class ReviewResult:
    """最终评审结果"""
    original_content: str
    final_content: str
    success: bool
    converged: bool
    iterations: List[ReviewIteration] = field(default_factory=list)
    final_score: float = 0.0
    initial_score: float = 0.0
    score_improvement: float = 0.0
    total_iterations: int = 0
    models_used: List[str] = field(default_factory=list)
    verdict: str = ""  # 最终评审结论
    error: Optional[str] = None

    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_content": self.original_content[:100] + "..." if len(self.original_content) > 100 else self.original_content,
            "final_content": self.final_content[:100] + "..." if len(self.final_content) > 100 else self.final_content,
            "success": self.success,
            "converged": self.converged,
            "iterations": [i.to_dict() for i in self.iterations],
            "final_score": self.final_score,
            "initial_score": self.initial_score,
            "score_improvement": self.score_improvement,
            "total_iterations": self.total_iterations,
            "models_used": self.models_used,
            "verdict": self.verdict,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        }


class ModelGatewayAdapter:
    """ModelGateway适配器 - 简化版"""

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
            # 解析模型名称
            model_name = self._resolve_model(model_id)
            content = self.gateway.chat(
                model_name=model_name,
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
        available = self.gateway.list_models()
        model_lower = model_id.lower()

        # 别名映射
        alias_map = {
            "claude": "claude-sonnet-4-20250514",
            "gpt4": "gpt-4o",
            "gpt-4": "gpt-4o",
            "gemini": "gemini-2-5-pro-preview-06-05",
        }

        if model_lower in alias_map:
            return alias_map[model_lower]

        if model_id in available:
            return model_id

        for avail in available:
            if model_lower in avail.lower():
                return avail

        return available[0] if available else "default"


class AutoReviewer:
    """自动评审循环

    支持:
    1. 多模型并行评审
    2. 迭代式改进
    3. 收敛判断
    4. 跨模型支持

    使用示例:
    ```python
    config = ReviewConfig(
        max_iterations=3,
        score_threshold=0.7,
        models=["gpt-4o", "claude-sonnet-4"],
    )

    reviewer = AutoReviewer(model_gateway, config)

    result = await reviewer.review(
        content="研究想法内容...",
        context="背景信息...",
    )

    print(f"Final score: {result.final_score}")
    print(f"Converged: {result.converged}")
    print(f"Improved content: {result.final_content}")
    ```
    """

    def __init__(
        self,
        model_gateway: Any,
        config: Optional[ReviewConfig] = None,
        custom_prompts: Optional[Dict[str, str]] = None,
    ):
        self.gateway = ModelGatewayAdapter(model_gateway)
        self.config = config or ReviewConfig()
        self.custom_prompts = custom_prompts or DEFAULT_REVIEW_PROMPTS

        # 合并自定义提示词
        if custom_prompts:
            self.custom_prompts = {**DEFAULT_REVIEW_PROMPTS, **custom_prompts}

    async def _call_review_model(
        self,
        model_id: str,
        content: str,
        context: str,
        role: str = "reviewer",
    ) -> ModelReviewResponse:
        """调用单个评审模型"""
        start_time = time.time()
        prompt = self.custom_prompts.get(role, self.custom_prompts["reviewer"])

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"""请评审以下内容:

{content}

背景信息:
{context}

请给出:
1. 各维度评分 (创新性、可行性、方法论、影响力、清晰度) - 每项0-10
2. 总体评价
3. 具体改进建议

格式:
评分:
- 创新性: X.X
- 可行性: X.X
- 方法论: X.X
- 影响力: X.X
- 清晰度: X.X

总体评分: X.X

评价: ...

建议: ..."""},
        ]

        try:
            response_text, duration_ms = await self.gateway.chat(
                model_id=model_id,
                messages=messages,
                temperature=0.3,
                max_tokens=1500,
            )

            scores = self._parse_scores(response_text)

            return ModelReviewResponse(
                model_id=model_id,
                content=response_text,
                scores=scores,
                innovation=scores.get("创新性", scores.get("innovation", 5.0)) / 10.0,
                feasibility=scores.get("可行性", scores.get("feasibility", 5.0)) / 10.0,
                methodology=scores.get("方法论", scores.get("methodology", 5.0)) / 10.0,
                impact=scores.get("影响力", scores.get("impact", 5.0)) / 10.0,
                clarity=scores.get("清晰度", scores.get("clarity", 5.0)) / 10.0,
                overall_score=scores.get("总体评分", scores.get("overall", 5.0)) / 10.0,
                success=True,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Review failed for {model_id}: {e}")
            return ModelReviewResponse(
                model_id=model_id,
                content="",
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _parse_scores(self, text: str) -> Dict[str, float]:
        """从评审文本解析评分"""
        import re
        scores = {}

        # 匹配各种评分格式
        patterns = [
            r'(?:创新性|Innovation)[:：]\s*([0-9.]+)',
            r'(?:可行性|Feasibility)[:：]\s*([0-9.]+)',
            r'(?:方法论|Methodology)[:：]\s*([0-9.]+)',
            r'(?:影响力|Impact)[:：]\s*([0-9.]+)',
            r'(?:清晰度|Clarity)[:：]\s*([0-9.]+)',
            r'(?:总体评分|Overall)[:：]\s*([0-9.]+)',
        ]

        keywords = ["创新性", "可行性", "方法论", "影响力", "清晰度", "总体评分",
                   "innovation", "feasibility", "methodology", "impact", "clarity", "overall"]

        for pattern, keyword in zip(patterns, keywords):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    scores[keyword] = float(match.group(1))
                except ValueError:
                    pass

        return scores

    async def _parallel_review(
        self,
        content: str,
        context: str,
    ) -> List[ModelReviewResponse]:
        """并行调用多个模型进行评审"""
        tasks = []
        for model_id in self.config.models:
            tasks.append(self._call_review_model(model_id, content, context))

        if self.config.parallel_reviews:
            results = await asyncio.gather(*tasks)
        else:
            results = []
            for task in tasks:
                result = await task
                results.append(result)

        return [r for r in results if r.success]

    def _aggregate_scores(
        self,
        reviews: List[ModelReviewResponse],
    ) -> Tuple[float, Dict[str, float]]:
        """聚合多个模型的评分"""
        if not reviews:
            return 0.0, {}

        # 计算各维度平均分
        dimensions = ["innovation", "feasibility", "methodology", "impact", "clarity"]
        aggregated = {}

        for dim in dimensions:
            scores = [getattr(r, dim, 0.0) for r in reviews if hasattr(r, dim)]
            if scores:
                aggregated[dim] = sum(scores) / len(scores)

        # 计算综合评分 (加权平均)
        weights = {
            "innovation": 0.25,
            "feasibility": 0.25,
            "methodology": 0.2,
            "impact": 0.15,
            "clarity": 0.15,
        }

        overall = sum(
            aggregated.get(dim, 0.5) * weights.get(dim, 0.0)
            for dim in dimensions
        )

        return overall, aggregated

    def _synthesize_review(
        self,
        content: str,
        reviews: List[ModelReviewResponse],
        aggregated_score: float,
    ) -> str:
        """综合评审意见"""
        if not reviews:
            return content

        # 取最佳评审作为主要参考
        best_review = max(reviews, key=lambda r: r.overall_score)

        synthesis_prompt = f"""基于以下多个模型的评审意见，请给出综合建议:

原始内容:
{content}

最佳评审意见:
{best_review.content}

请根据评审意见，改进原始内容，生成更完善的版本。
只输出改进后的内容，不需要解释。"""

        # 使用第一个模型的配置
        try:
            model_id = self.config.models[0]
            messages = [
                {"role": "user", "content": synthesis_prompt},
            ]
            improved_content, _ = asyncio.get_event_loop().run_until_complete(
                self.gateway.chat(model_id, messages, temperature=0.7, max_tokens=2000)
            )
            return improved_content.strip()
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            return content

    async def _improve_content(
        self,
        content: str,
        reviews: List[ModelReviewResponse],
        aggregated_score: float,
    ) -> str:
        """根据评审意见改进内容"""
        if not reviews:
            return content

        # 收集所有评审意见
        all_feedback = "\n\n".join([
            f"[{r.model_id}] 评分: {r.overall_score:.2f}\n{r.content}"
            for r in reviews
        ])

        improvement_prompt = f"""你是一位研究论文改进专家。

原始内容:
{content}

评审意见汇总:
{all_feedback}

当前评分: {aggregated_score:.2f}/1.0

请根据评审意见，生成改进后的内容。
要求:
1. 保留原始内容的核心思想
2. 吸收评审中的合理建议
3. 改进评审指出的不足
4. 只输出改进后的内容，不要其他解释
"""

        try:
            # 使用综合评分最高的模型来改进
            best_model = max(reviews, key=lambda r: r.overall_score)
            messages = [{"role": "user", "content": improvement_prompt}]

            improved, _ = await self.gateway.chat(
                best_model.model_id,
                messages,
                temperature=self.config.improvement_strength,
                max_tokens=2000,
            )

            return improved.strip()

        except Exception as e:
            logger.warning(f"Content improvement failed: {e}")
            return content

    async def review(
        self,
        content: str,
        context: str = "",
    ) -> ReviewResult:
        """运行自动评审循环

        Args:
            content: 要评审的内容
            context: 背景信息

        Returns:
            ReviewResult: 评审结果
        """
        result = ReviewResult(
            original_content=content,
            final_content=content,
            success=True,
            converged=False,
            models_used=self.config.models.copy(),
        )

        start_time = time.time()
        current_content = content
        prev_score = 0.0

        logger.info(f"Starting auto review: max_iterations={self.config.max_iterations}, threshold={self.config.score_threshold}")

        for iteration in range(1, self.config.max_iterations + 1):
            logger.info(f"Review iteration {iteration}/{self.config.max_iterations}")

            # 并行评审
            reviews = await self._parallel_review(current_content, context)

            if not reviews:
                logger.warning(f"No successful reviews in iteration {iteration}")
                break

            # 聚合评分
            aggregated_score, dimension_scores = self._aggregate_scores(reviews)

            # 创建迭代记录
            iteration_record = ReviewIteration(
                iteration=iteration,
                content=current_content,
                reviews=reviews,
                aggregated_score=aggregated_score,
                score_delta=aggregated_score - prev_score,
            )

            # 检查是否收敛
            if iteration > 1:
                score_change = abs(aggregated_score - prev_score)
                if score_change < 0.05:  # 分数变化小于5%
                    iteration_record.converged = True
                    logger.info(f"Converged at iteration {iteration}: score change {score_change:.3f}")
                    current_content = self._synthesize_review(current_content, reviews, aggregated_score)
                    iteration_record.improved_content = current_content
                    result.iterations.append(iteration_record)
                    break

            # 检查是否达到阈值
            if aggregated_score >= self.config.score_threshold:
                logger.info(f"Threshold reached: {aggregated_score:.2f} >= {self.config.score_threshold}")
                iteration_record.converged = True
                current_content = self._synthesize_review(current_content, reviews, aggregated_score)
                iteration_record.improved_content = current_content
                result.iterations.append(iteration_record)
                break

            prev_score = aggregated_score
            result.iterations.append(iteration_record)

            # 继续改进
            if iteration < self.config.max_iterations:
                improved = await self._improve_content(current_content, reviews, aggregated_score)
                current_content = improved
                iteration_record.improved_content = improved

        # 计算最终结果
        result.final_content = current_content
        result.total_iterations = len(result.iterations)

        if result.iterations:
            result.final_score = result.iterations[-1].aggregated_score
            result.initial_score = result.iterations[0].aggregated_score
            result.score_improvement = result.final_score - result.initial_score
            result.converged = any(i.converged for i in result.iterations)

        result.completed_at = datetime.now(timezone.utc).isoformat() + "Z"
        result.duration_seconds = time.time() - start_time

        logger.info(
            f"Auto review completed: iterations={result.total_iterations}, "
            f"final_score={result.final_score:.2f}, "
            f"improvement={result.score_improvement:.2f}, "
            f"converged={result.converged}"
        )

        return result

    def review_sync(
        self,
        content: str,
        context: str = "",
    ) -> ReviewResult:
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


def get_default_review_config(
    models: Optional[List[str]] = None,
    max_iterations: int = 3,
    score_threshold: float = 0.7,
) -> ReviewConfig:
    """获取默认评审配置

    Args:
        models: 评审模型列表 (默认使用异构配置)
        max_iterations: 最大迭代次数
        score_threshold: 通过阈值
    """
    return ReviewConfig(
        models=models or ["gpt-4o", "claude-sonnet-4"],
        max_iterations=max_iterations,
        score_threshold=score_threshold,
        parallel_reviews=True,
        improvement_strength=0.8,
    )


def create_auto_reviewer(
    model_gateway: Any,
    models: Optional[List[str]] = None,
    **kwargs,
) -> AutoReviewer:
    """创建自动评审器的便捷函数

    Example:
        reviewer = create_auto_reviewer(
            gateway,
            models=["gpt-4o", "claude-sonnet-4", "gemini"],
            max_iterations=3,
            score_threshold=0.7,
        )
    """
    config = get_default_review_config(models=models, **kwargs)
    return AutoReviewer(model_gateway, config)
