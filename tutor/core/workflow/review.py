"""ReviewFlow - 论文审核校验工作流

对完成的实验进行多维度审核，评估论文的创新点、工程质量和学术表达。

支持三种评审模式:
1. 单角色审核 (MVP) - 单一模型完成
2. 跨模型对抗评审 - 不同模型辩论式评审
3. 自动评审循环 - 迭代式改进直到收敛

配置:
- review_mode: 评审模式 ("single", "cross_model", "auto_loop")
- cross_model_config: 跨模型配置
- auto_review_config: 自动评审配置
"""

import logging
from typing import List, Dict, Any, Optional

from tutor.core.workflow import Workflow, WorkflowStep, WorkflowContext
from tutor.core.model import ModelGateway
from tutor.core.storage import StorageManager
from tutor.core.review import (
    AutoReviewer,
    CrossModelReviewer,
    ReviewConfig,
)

logger = logging.getLogger(__name__)


def _build_paper_prompt(title: str, abstract: str, introduction: str,
                         methodology: str, experiments: str, conclusion: str,
                         experiment_report: Dict = None) -> str:
    """构建论文评审提示"""
    return f"""Please perform a comprehensive academic review of the following research paper.

**Paper Title:** {title}

**Abstract:**
{abstract}

**1. Introduction**
{introduction}

**2. Methodology**
{methodology}

**3. Experiments**
{experiments}

**4. Conclusion**
{conclusion}

{f"**Related Experiment Report:**\n{experiment_report.get('final_report', '')[:1000]}..." if experiment_report else ""}

Please evaluate the paper on the following dimensions and provide specific feedback:

### Dimensions:
1. **Originality/Innovation** (0-10): How novel is the contribution?
2. **Methodological Rigor** (0-10): Is the methodology sound and well-described?
3. **Experimental Completeness** (0-10): Are experiments adequate and reproducible?
4. **Writing Quality** (0-10): Is the paper well-written and organized?
5. **Significance** (0-10): How important is the work?

For each dimension, provide:
- Score (0-10)
- Strengths
- Weaknesses
- Specific suggestions for improvement

Also provide:
- **Overall Recommendation**: Accept / Minor Revisions / Major Revisions / Reject
- **Key Contribution Summary**: What is the core contribution?
- **Critical Issues**: List any fatal flaws that must be addressed.

Format your response as a structured review."""


def _parse_review(scores: Dict[str, float], recommendation: str,
                  key_contribution: str) -> tuple[Dict[str, float], str, str]:
    """解析评论文本，提取评分和推荐"""
    import re

    parsed_scores = {}
    # 提取各维度评分
    dimensions = ["originality", "methodological_rigor", "experimental_completeness",
                   "writing_quality", "significance"]

    for dim in dimensions:
        if dim in scores:
            score = scores[dim]
            # 归一化到0-1
            if score > 1:
                score = score / 10
            parsed_scores[dim] = score

    # 如果未提取到评分，给默认值
    if len(parsed_scores) < 3:
        logger.warning("Failed to extract scores from review, using defaults")
        for dim in dimensions:
            if dim not in parsed_scores:
                parsed_scores[dim] = 0.5

    return parsed_scores, recommendation, key_contribution


class PaperReviewStep(WorkflowStep):
    """论文审核步骤

    支持三种评审模式:
    1. "single" (默认): 单角色审核，单一模型完成
    2. "cross_model": 跨模型对抗评审 (Advocate vs Critic)
    3. "auto_loop": 自动评审循环 (迭代改进直到收敛)

    配置:
    - review_mode: 评审模式
    - cross_model_config: 跨模型配置 {"primary": str, "critic": str, "synthesizer": str}
    - auto_review_config: 自动评审配置 (ReviewConfig格式)

    输出状态:
    - review_feedback: Dict - 结构化反馈
    - scores: Dict - 各维度评分
    - overall_score: float - 总体评分
    - cross_model_result: 跨模型评审结果 (如果启用)
    """

    def __init__(
        self,
        model_gateway: ModelGateway,
        review_mode: str = "single",
        cross_model_config: Optional[Dict[str, str]] = None,
        auto_review_config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            name="paper_review",
            description=f"Paper review (mode: {review_mode})"
        )
        self.model_gateway = model_gateway
        self.review_mode = review_mode
        self.cross_model_config = cross_model_config
        self.auto_review_config = auto_review_config

    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行论文审核"""
        paper_content = context.get_state("paper_content", {})
        experiment_report = context.get_state("experiment_report", {})

        if not paper_content:
            raise ValueError("No paper_content found. Please provide paper content first.")

        logger.info(f"Starting paper review... mode={self.review_mode}")

        # 根据模式选择评审方法
        if self.review_mode == "cross_model":
            return self._review_cross_model(paper_content, experiment_report)
        elif self.review_mode == "auto_loop":
            return self._review_auto_loop(paper_content, experiment_report)
        else:
            return self._review_single(paper_content, experiment_report)

    def _review_single(self, paper_content: Dict, experiment_report: Dict) -> Dict[str, Any]:
        """单角色评审 (MVP)"""
        # 提取论文各部分
        title = paper_content.get("title", "Untitled")
        abstract = paper_content.get("abstract", "")
        introduction = paper_content.get("introduction", "")
        methodology = paper_content.get("methodology", "")
        experiments = paper_content.get("experiments", "")
        conclusion = paper_content.get("conclusion", "")

        prompt = _build_paper_prompt(
            title, abstract, introduction, methodology, experiments, conclusion,
            experiment_report
        )

        try:
            response = self.model_gateway.chat(
                "reviewer",
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1500
            )

            review_text = response.strip()

            # 解析评分和推荐
            scores, recommendation, key_contribution = self._parse_review_text(review_text)

            result = {
                "review_text": review_text,
                "scores": scores,
                "overall_score": sum(scores.values()) / len(scores) if scores else 0,
                "recommendation": recommendation,
                "key_contribution": key_contribution,
                "reviewer": "single-role-mvp",
                "review_mode": "single",
            }

            logger.info(
                f"Paper review complete: overall_score={result['overall_score']:.2f}, "
                f"recommendation={recommendation}"
            )

            return result

        except Exception as e:
            logger.error(f"Paper review failed: {e}")
            raise

    def _review_cross_model(self, paper_content: Dict, experiment_report: Dict) -> Dict[str, Any]:
        """跨模型对抗评审"""
        # 提取论文内容
        title = paper_content.get("title", "Untitled")
        abstract = paper_content.get("abstract", "")
        full_text = f"Title: {title}\n\nAbstract: {abstract}"

        if paper_content.get("introduction"):
            full_text += f"\n\nIntroduction: {paper_content.get('introduction', '')[:500]}"
        if paper_content.get("methodology"):
            full_text += f"\n\nMethodology: {paper_content.get('methodology', '')[:500]}"
        if paper_content.get("experiments"):
            full_text += f"\n\nExperiments: {paper_content.get('experiments', '')[:500]}"

        # 获取模型配置
        config = self.cross_model_config or {
            "primary": "claude-sonnet-4",
            "critic": "gpt-4o",
            "synthesizer": "gpt-4o",
        }

        # 创建跨模型评审器
        reviewer = CrossModelReviewer(
            model_gateway=self.model_gateway,
            primary_model=config.get("primary", "claude-sonnet-4"),
            critic_model=config.get("critic", "gpt-4o"),
            synthesizer_model=config.get("synthesizer", "gpt-4o"),
        )

        try:
            result = reviewer.review_sync(full_text, context=str(experiment_report))

            # 转换结果格式
            review_result = {
                "review_text": result.synthesis_response.content if result.synthesis_response else "",
                "scores": {
                    "overall": result.final_score,
                    "initial": result.initial_score,
                },
                "overall_score": result.final_score,
                "recommendation": result.verdict.final_verdict[:100] if result.verdict else "Unknown",
                "key_contribution": "",
                "reviewer": f"cross-model ({result.primary_model} vs {result.critic_model})",
                "review_mode": "cross_model",
                "cross_model_meta": {
                    "primary_model": result.primary_model,
                    "critic_model": result.critic_model,
                    "synthesizer_model": result.synthesizer_model,
                    "vendors_used": result.vendors_used,
                    "mode": result.mode,
                    "advocate_content": result.advocate_response.content[:500] if result.advocate_response else "",
                    "critic_content": result.critic_response.content[:500] if result.critic_response else "",
                    "score_improvement": result.score_improvement,
                },
                "cross_model_result": result.to_dict(),
            }

            if result.verdict:
                review_result["scores"]["confidence"] = result.verdict.confidence
                review_result["scores"]["strengths"] = result.verdict.strengths[:3]
                review_result["scores"]["weaknesses"] = result.verdict.weaknesses[:3]

            logger.info(
                f"Cross-model review complete: score={result.final_score:.2f}, "
                f"vendors={result.vendors_used}"
            )

            return review_result

        except Exception as e:
            logger.error(f"Cross-model review failed: {e}")
            # 回退到单角色评审
            logger.info("Falling back to single-role review")
            return self._review_single(paper_content, experiment_report)

    def _review_auto_loop(self, paper_content: Dict, experiment_report: Dict) -> Dict[str, Any]:
        """自动评审循环"""
        # 提取论文内容
        title = paper_content.get("title", "Untitled")
        abstract = paper_content.get("abstract", "")
        full_text = f"Title: {title}\n\nAbstract: {abstract}"

        if paper_content.get("introduction"):
            full_text += f"\n\nIntroduction: {paper_content.get('introduction', '')}"
        if paper_content.get("methodology"):
            full_text += f"\n\nMethodology: {paper_content.get('methodology', '')}"
        if paper_content.get("experiments"):
            full_text += f"\n\nExperiments: {paper_content.get('experiments', '')}"

        # 获取配置
        config = self.auto_review_config or {}
        models = config.get("models", ["gpt-4o", "claude-sonnet-4"])

        # 创建自动评审器
        review_config = ReviewConfig(
            max_iterations=config.get("max_iterations", 3),
            score_threshold=config.get("score_threshold", 0.7),
            models=models,
            parallel_reviews=True,
            improvement_strength=config.get("improvement_strength", 0.8),
        )

        reviewer = AutoReviewer(
            model_gateway=self.model_gateway,
            config=review_config,
        )

        try:
            result = reviewer.review_sync(
                content=full_text,
                context=str(experiment_report)[:500] if experiment_report else "",
            )

            # 转换结果格式
            review_result = {
                "review_text": result.iterations[-1].reviews[0].content if result.iterations else "",
                "scores": {
                    "initial": result.initial_score,
                    "final": result.final_score,
                    "improvement": result.score_improvement,
                },
                "overall_score": result.final_score,
                "recommendation": "Accepted" if result.converged else "Needs Revision",
                "key_contribution": "",
                "reviewer": f"auto-loop ({', '.join(models)})",
                "review_mode": "auto_loop",
                "auto_review_meta": {
                    "total_iterations": result.total_iterations,
                    "converged": result.converged,
                    "score_threshold": review_config.score_threshold,
                    "models_used": result.models_used,
                    "iterations": [i.to_dict() for i in result.iterations],
                },
                "auto_review_result": result.to_dict(),
            }

            logger.info(
                f"Auto review complete: iterations={result.total_iterations}, "
                f"final_score={result.final_score:.2f}, converged={result.converged}"
            )

            return review_result

        except Exception as e:
            logger.error(f"Auto review failed: {e}")
            # 回退到单角色评审
            logger.info("Falling back to single-role review")
            return self._review_single(paper_content, experiment_report)

    def _parse_review_text(self, review_text: str) -> tuple[Dict[str, float], str, str]:
        """解析评论文本，提取评分和推荐"""
        import re

        scores = {}
        # 提取各维度评分
        dimensions = ["Originality", "Methodological Rigor", "Experimental Completeness",
                       "Writing Quality", "Significance"]

        for dim in dimensions:
            patterns = [
                rf'{dim}.*?(\d+(?:\.\d+)?)(?:/10)?',
                rf'{dim}\*?:\s*(\d+(?:\.\d+)?)(?:/10)?',
                rf'{dim}\s*-\s*(\d+(?:\.\d+)?)(?:/10)?'
            ]
            for pattern in patterns:
                match = re.search(pattern, review_text, re.IGNORECASE)
                if match:
                    try:
                        score = float(match.group(1))
                        # 归一化到0-1范围
                        if score > 1:
                            score = score / 10
                        scores[dim.lower().replace(" ", "_")] = score
                        break
                    except ValueError:
                        pass

        # 如果未提取到评分，给默认值
        if len(scores) < 3:
            logger.warning("Failed to extract scores from review, using defaults")
            for dim in dimensions:
                key = dim.lower().replace(" ", "_")
                if key not in scores:
                    scores[key] = 0.5

        # 提取推荐决定
        recommendation = "Needs Revision"
        rec_patterns = [
            r'Recommendation:\s*(Accept|Minor Revisions|Major Revisions|Reject)',
            r'Overall Recommendation:\s*(Accept|Minor Revisions|Major Revisions|Reject)',
            r'decision:\s*(accept|reject|revise)'
        ]
        for pattern in rec_patterns:
            match = re.search(pattern, review_text, re.IGNORECASE)
            if match:
                recommendation = match.group(1).title()
                break

        # 提取核心贡献
        key_contribution = ""
        contrib_match = re.search(
            r'(?:Core|Key) Contribution:?\s*(.+?)(?=\n\n|\n\*\*|$)',
            review_text, re.DOTALL | re.IGNORECASE
        )
        if contrib_match:
            key_contribution = contrib_match.group(1).strip()
        else:
            key_contribution = review_text[:200]

        return scores, recommendation, key_contribution

    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        if not context.get_state("paper_content"):
            errors.append("No paper_content found. Please provide the paper to review.")
        return errors


class ReviewFlow(Workflow):
    """ReviewFlow - 论文审核校验工作流

    完整工作流:
    1. 论文接收（用户提供）
    2. 多角色审核 (可配置模式)
    3. 生成反馈报告

    支持的评审模式:
    - "single": 单角色审核 (MVP)
    - "cross_model": 跨模型对抗评审
    - "auto_loop": 自动评审循环
    """

    def __init__(
        self,
        workflow_id: str,
        config: Dict[str, Any],
        storage_path,
        model_gateway: ModelGateway,
        **kwargs
    ):
        super().__init__(
            workflow_id=workflow_id,
            config=config,
            storage_path=storage_path,
            model_gateway=model_gateway,
            **kwargs
        )
        self.review_mode = config.get("review_mode", "single")
        self.cross_model_config = config.get("cross_model_config")
        self.auto_review_config = config.get("auto_review_config")

    def build_steps(self) -> List[WorkflowStep]:
        """构建工作流步骤"""
        steps = [
            PaperReviewStep(
                self.model_gateway,
                review_mode=self.review_mode,
                cross_model_config=self.cross_model_config,
                auto_review_config=self.auto_review_config,
            ),
        ]
        return steps

    def run_review(self, paper_content: Dict[str, Any]) -> Dict[str, Any]:
        """简化入口：直接审核论文

        方便CLI调用，不经过完整Workflow引擎。

        Args:
            paper_content: 论文内容字典

        Returns:
            审核结果
        """
        # 创建临时context
        context = WorkflowContext(
            workflow_id=f"review_{id(self)}",
            config=self.config,
            storage_path=self.storage_path,
            model_gateway=self.model_gateway
        )

        # 设置状态
        context.set_state("paper_content", paper_content)

        # 运行PaperReviewStep
        review_step = PaperReviewStep(
            self.model_gateway,
            review_mode=self.review_mode,
            cross_model_config=self.cross_model_config,
            auto_review_config=self.auto_review_config,
        )
        result = review_step.execute(context)

        return result


__all__ = [
    'ReviewFlow',
    'PaperReviewStep',
]
