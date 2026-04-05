"""IdeaFlow - 研究想法生成工作流

工作流程:
1. paper_loading - 加载用户提供的文献
2. paper_validation - 验证文献质量
3. literature_analysis - AI分析文献，提取知识图谱
4. idea_debate - 多角色辩论生成创新想法
5. idea_evaluation - 评估想法的可行性和创新性
6. final_proposal - 生成最终研究提案

配置示例:
```yaml
workflow:
  type: idea
  steps: 6
  paper_sources:
    - "papers/paper1.pdf"
    - "https://arxiv.org/abs/2301.00001"
  debate_rounds: 2
  evaluator_model: "evaluator"
```
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from tutor.core.workflow.base import Workflow, WorkflowStep, WorkflowContext
from tutor.core.workflow.project_gate import ProjectGateStep
from tutor.core.workflow.steps.paper_loading import (
    PaperLoadingStep,
    PaperValidationStep,
)
from tutor.core.workflow.steps.zotero_literature import ZoteroLiteratureStep
from tutor.core.workflow.steps.smart_input import (
    SmartInputStep,
    AutoArxivSearchStep,
)
from tutor.core.workflow.debate_framework import (
    MultiDimensionalDebate,
    DebatePosition,
    Argument,
    DimensionType,
    ArgumentEvaluator,
    build_research_debate_positions,
)
from tutor.core.model import ModelGateway
from tutor.core.debate import (
    CrossModelDebater,
    DebateModelConfig,
    ModuleModelConfig,
    get_default_debate_config,
    DebateRole,
    create_cross_model_debater,
)

logger = logging.getLogger(__name__)


class LiteratureAnalysisStep(WorkflowStep):
    """文献分析步骤
    
    AI分析已加载的文献，提取：
    - 研究问题和假设
    - 方法论
    - 关键发现
    - 知识空白
    - 相关概念和术语
    
    输出状态：
    - literature_analysis: Dict - 分析结果
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="literature_analysis",
            description="AI analysis of loaded papers to extract research landscape"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行文献分析
        
        使用模型分析所有验证通过的论文。
        
        Returns:
            {
                "analysis": {
                    "total_papers": int,
                    "key_concepts": List[str],
                    "research_questions": List[str],
                    "methodologies": List[str],
                    "findings": List[str],
                    "gaps": List[str],
                    "paper_analyses": [{"title": str, "analysis": str}, ...]
                }
            }
        """
        papers = context.get_state("validated_papers", [])
        
        if not papers:
            raise ValueError("No validated papers found for analysis")
        
        logger.info(f"Analyzing {len(papers)} papers")

        all_analyses = []
        key_concepts = set()
        research_questions = set()
        methodologies = set()
        findings = set()
        gaps = set()

        def analyze_paper_wrapper(paper):
            """包装函数用于并行执行"""
            # Handle both dict (from checkpoint) and PaperMetadata object
            if isinstance(paper, dict):
                paper_title = paper.get('title', 'Unknown')
                paper_authors = paper.get('authors', [])
                paper_abstract = paper.get('abstract', '')
                paper_raw_text = paper.get('raw_text', '')
            else:
                paper_title = paper.title
                paper_authors = paper.authors
                paper_abstract = paper.abstract
                paper_raw_text = paper.raw_text

            logger.info(f"Analyzing paper: {paper_title}")
            analysis = self._analyze_single_paper(paper)
            return {
                "title": paper_title,
                "authors": paper_authors,
                "analysis": analysis
            }

        with ThreadPoolExecutor(max_workers=max(1, min(4, len(papers)))) as executor:
            futures = {executor.submit(analyze_paper_wrapper, paper): paper for paper in papers}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    all_analyses.append(result)
                    # 并行提取关键信息
                    self._extract_concepts(result["analysis"], key_concepts)
                    self._extract_questions(result["analysis"], research_questions)
                    self._extract_methodologies(result["analysis"], methodologies)
                    self._extract_findings(result["analysis"], findings)
                    self._extract_gaps(result["analysis"], gaps)
                except Exception as e:
                    logger.error(f"Failed to analyze paper: {e}")
        
        # 汇总分析
        summary = {
            "total_papers": len(papers),
            "key_concepts": list(key_concepts)[:20],  # 限制数量
            "research_questions": list(research_questions)[:10],
            "methodologies": list(methodologies)[:10],
            "findings": list(findings)[:10],
            "gaps": list(gaps)[:10],
        }
        
        result = {
            "literature_analysis": {
                "analysis": summary,
                "paper_analyses": all_analyses,
                "concepts": list(key_concepts)
            }
        }

        logger.info(f"Literature analysis complete: {len(key_concepts)} concepts identified")

        return result
    
    def _analyze_single_paper(self, paper) -> str:
        """分析单篇论文

        Args:
            paper: PaperMetadata对象或dict（来自检查点恢复）
        """
        # Handle both dict (from checkpoint) and PaperMetadata object
        if isinstance(paper, dict):
            raw_text = paper.get('raw_text', '')
            title = paper.get('title', 'Unknown')
            authors = paper.get('authors', [])
            abstract = paper.get('abstract', '')
        else:
            raw_text = paper.raw_text
            title = paper.title
            authors = paper.authors
            abstract = paper.abstract

        # 截取前2000字符避免token限制
        text = raw_text[:2000] if raw_text else ""

        prompt = f"""
Analyze the following research paper and provide structured insights.

Paper Title: {title}
Authors: {', '.join(authors)}
Abstract: {abstract}

Full Text (first 2000 chars):
{text}

Please provide analysis covering:
1. Main research question or problem
2. Methodology used
3. Key findings
4. Limitations mentioned
5. Future work suggested

Format your response as a coherent analysis.
"""

        try:
            response = self.model_gateway.chat(
                "analyzer",
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000
            )
            return response
        except Exception as e:
            logger.error(f"Failed to analyze paper '{title}': {e}")
            return f"Analysis failed: {e}"
    
    def _extract_info(self, analysis: str, info_set: set, keywords: list[str]):
        """通用信息提取 - 支持Markdown格式和冒号格式

        支持两种格式:
        1. Markdown: **1. Title** 或 **Title** 后面跟内容
        2. 冒号分隔: keyword: content
        """
        import re

        # 方法1: 提取 Markdown 标题后的内容
        # 匹配 **N. Title** 或 **Title** 格式
        md_pattern = r'\*\*(?:\d+\.\s*)?([^*]+)\*\*\s*\n(.+?)(?=\n\s*\*\*|\n\n|\Z)'
        md_matches = re.findall(md_pattern, analysis, re.DOTALL | re.IGNORECASE)

        for title, content in md_matches:
            title_lower = title.lower().strip()
            # 检查标题是否包含任意一个关键词
            for keyword in keywords:
                if keyword in title_lower:
                    extracted = content.strip()
                    if extracted and len(extracted) > 10:
                        info_set.add(extracted[:200])
                    break

        # 方法2: 冒号分隔格式 (原始逻辑)
        for keyword in keywords:
            pattern = rf'(?:^|\n)\s*{re.escape(keyword)}[:\s]*(.+?)(?=\n[A-Z]|$)'
            matches = re.findall(pattern, analysis, re.IGNORECASE | re.DOTALL)
            for match in matches:
                extracted = match.strip()
                if extracted and len(extracted) > 10:
                    info_set.add(extracted[:200])

    def _extract_concepts(self, analysis: str, concepts: set):
        """从分析文本提取概念"""
        keywords = ['concept', 'framework', 'theory', 'model', 'approach']
        self._extract_info(analysis, concepts, keywords)

    def _extract_questions(self, analysis: str, questions: set):
        """提取研究问题"""
        keywords = ['research question', 'problem', 'objective', 'aim']
        self._extract_info(analysis, questions, keywords)

    def _extract_methodologies(self, analysis: str, methodologies: set):
        """提取方法论"""
        keywords = ['methodology', 'method', 'approach', 'technique']
        self._extract_info(analysis, methodologies, keywords)

    def _extract_findings(self, analysis: str, findings: set):
        """提取关键发现"""
        keywords = ['finding', 'result', 'outcome', 'discovered']
        self._extract_info(analysis, findings, keywords)

    def _extract_gaps(self, analysis: str, gaps: set):
        """提取研究空白"""
        keywords = ['gap', 'limitation', 'future', 'challenge', 'opportunity']
        self._extract_info(analysis, gaps, keywords)


class IdeaDebateStep(WorkflowStep):
    """想法辩论步骤

    多个AI角色（不同研究方向）就研究空白进行辩论，
    生成多个创新研究想法。

    支持两种模式:
    1. 原生辩论 (默认): 使用单个模型，角色通过不同prompt区分
    2. 跨模型辩论: 使用多个不同模型，实现真正的视角多样性

    配置:
    - debate_rounds: 辩论轮数（默认2）
    - cross_model_debate: 是否启用跨模型辩论 (默认False)
    - cross_model_config: 跨模型配置 (可选)

    跨模型配置示例:
    ```python
    # 异构模式 (2+模型)
    cross_model_config = {
        "innovator": ["claude-sonnet-4"],
        "skeptic": ["gpt-4o"],
        "pragmatist": ["gemini-2-5-pro"],
        "expert": ["claude-sonnet-4"],
        "synthesizer": ["gpt-4o"],
    }

    # 单模型回退模式 (只有1个模型会自动复用)
    cross_model_config = {
        "innovator": ["gpt-4o"],
        "skeptic": ["gpt-4o"],  # 会自动回退到单模型模式
        "synthesizer": ["gpt-4o"],
    }
    ```

    输出状态：
    - debate_ideas: List[Dict] - 辩论产生的想法
    - cross_model_result: 跨模型辩论结果 (如果启用)
    """

    def __init__(
        self,
        model_gateway: ModelGateway,
        config: Dict[str, Any],
        cross_model_config: Optional[Dict[str, List[str]]] = None,
    ):
        super().__init__(
            name="idea_debate",
            description="Multi-role debate to generate innovative research ideas"
        )
        self.model_gateway = model_gateway
        self.debate_rounds = config.get("debate_rounds", 2)
        self.roles = self._define_roles()

        # 跨模型辩论配置
        self.cross_model_enabled = config.get("cross_model_debate", False)
        self.cross_model_config = cross_model_config or config.get("cross_model_config")

        # 初始化跨模型辩论器 (如果启用)
        self._cross_model_debater: Optional[CrossModelDebater] = None
        if self.cross_model_enabled and self.cross_model_config:
            self._init_cross_model_debater()
    
    def _define_roles(self) -> List[Dict[str, str]]:
        """定义辩论角色"""
        return [
            {
                "name": "Innovator",
                "persona": "You are a creative researcher who loves exploring novel ideas and breakthrough approaches. Think outside the box.",
                "goal": "Propose innovative and ambitious research ideas",
                "description": "Creative researcher proposing innovative ideas"
            },
            {
                "name": "Skeptic",
                "persona": "You are a critical thinker who challenges assumptions and identifies potential flaws. Be constructive but rigorous.",
                "goal": "Critique ideas and identify risks or weaknesses",
                "description": "Critical thinker challenging assumptions"
            },
            {
                "name": "Pragmatist",
                "persona": "You are a practical researcher focused on feasibility and implementation. Consider resources, timeline, and technical challenges.",
                "goal": "Evaluate feasibility and propose practical improvements",
                "description": "Practical researcher evaluating feasibility"
            },
            {
                "name": "Expert",
                "persona": "You are a domain expert with deep knowledge of the field. Provide insights on related work and state-of-the-art.",
                "goal": "Ensure ideas are grounded in current research and identify relevant literature",
                "description": "Domain expert providing research insights"
            }
        ]

    def _init_cross_model_debater(self) -> None:
        """初始化跨模型辩论器"""
        try:
            self._cross_model_debater = create_cross_model_debater(
                model_gateway=self.model_gateway,
                module_name="idea_debate",
                role_model_map=self.cross_model_config,
                debate_rounds=self.debate_rounds,
                enable_cross_examination=True,
            )
            logger.info(
                f"Cross-model debater initialized: "
                f"mode={self._cross_model_debater.mode}, "
                f"config={self.cross_model_config}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize cross-model debater: {e}")
            self._cross_model_debater = None
            self.cross_model_enabled = False

    def _execute_cross_model_debate(
        self,
        ideas: List[str],
        analysis: Dict[str, Any],
        context: WorkflowContext,
    ) -> Dict[str, Any]:
        """执行跨模型辩论

        使用CrossModelDebater进行真正的多模型辩论

        Args:
            ideas: 要辩论的想法列表
            analysis: 文献分析结果
            context: 工作流上下文

        Returns:
            包含辩论结果的字典
        """
        context_summary = self._summarize_analysis(analysis)
        gaps = analysis.get("analysis", {}).get("gaps", [])
        concepts = context.get_state("concepts", [])

        # 构建辩论主题
        topic = f"""研究空白: {'; '.join(gaps[:3])}
相关概念: {', '.join(concepts[:10])}"""

        debated_ideas = []

        for i, idea in enumerate(ideas):
            logger.info(f"Cross-model debating idea {i+1}/{len(ideas)}: {idea[:50]}...")

            try:
                # 运行跨模型辩论
                debate_result = self._cross_model_debater.debate_sync(
                    topic=f"""现有研究想法:
{idea}

研究背景:
{topic}""",
                    context=context_summary,
                    rounds=self.debate_rounds,
                )

                # 处理 dict（检查点恢复）vs 对象格式
                if isinstance(debate_result, dict):
                    # 从检查点恢复的 dict 格式
                    dr_final_conclusion = debate_result.get("final_conclusion", "")
                    dr_turns = debate_result.get("turns", [])
                    dr_key_args = debate_result.get("key_arguments", [])
                    dr_counter_args = debate_result.get("counter_arguments", [])
                    dr_overall_score = debate_result.get("overall_score", 0.0)
                    dr_mode = debate_result.get("mode", "heterogeneous")
                    dr_models_used = debate_result.get("models_used", [])
                    dr_vendors_used = debate_result.get("vendors_used", [])
                    dr_confidence = debate_result.get("confidence_level", "low")
                    dr_total_rounds = debate_result.get("total_rounds", 0)
                    cross_model_dict = debate_result
                else:
                    # 正常的 DebateResult 对象
                    dr_final_conclusion = debate_result.final_conclusion
                    dr_turns = debate_result.turns
                    dr_key_args = debate_result.key_arguments
                    dr_counter_args = debate_result.counter_arguments
                    dr_overall_score = debate_result.overall_score
                    dr_mode = debate_result.mode
                    dr_models_used = debate_result.models_used
                    dr_vendors_used = debate_result.vendors_used
                    dr_confidence = debate_result.confidence_level
                    dr_total_rounds = debate_result.total_rounds
                    cross_model_dict = debate_result.to_dict()

                # 转换为兼容格式
                debate_log = []
                for turn in dr_turns:
                    if isinstance(turn, dict):
                        # Dict from checkpoint
                        role = turn.get("speaker_role", "")
                        role_value = role.value if hasattr(role, "value") else str(role)
                        debate_log.append({
                            "role": role_value,
                            "content": turn.get("content", ""),
                            "model": turn.get("speaker_model", ""),
                            "round": turn.get("round_number", turn.get("round", 0)),
                        })
                    else:
                        # DebateTurn object
                        debate_log.append({
                            "role": turn.speaker_role.value,
                            "content": turn.content,
                            "model": turn.speaker_model,
                            "round": turn.round_number,
                        })

                debated_idea = {
                    "original_idea": idea,
                    "final_idea": dr_final_conclusion or idea,
                    "debate_log": debate_log,
                    "pros": dr_key_args,
                    "cons": dr_counter_args,
                    "innovation": dr_overall_score,
                    "feasibility": dr_overall_score * 0.9,  # 简化估算
                    # 跨模型特有字段
                    "cross_model_result": cross_model_dict,
                    "debate_mode": dr_mode,
                    "models_used": dr_models_used,
                    "vendors_used": dr_vendors_used,
                    "confidence_level": dr_confidence,
                    "total_rounds": dr_total_rounds,
                    # 辩论质量评估（设计文档建议）
                    "debate_quality": self._assess_debate_quality(
                        debate_log, idea, dr_final_conclusion or idea,
                        dr_key_args, dr_counter_args, cross_model_dict
                    ),
                }
                debated_ideas.append(debated_idea)

            except Exception as e:
                logger.error(f"Cross-model debate failed for idea {i+1}: {e}")
                # 回退到原生辩论
                debate_log = self._run_debate(idea, analysis)
                final_version = self._synthesize_final_idea(idea, debate_log)
                pros = self._extract_pros(debate_log)
                cons = self._extract_cons(debate_log)
                debated_ideas.append({
                    "original_idea": idea,
                    "final_idea": final_version,
                    "debate_log": debate_log,
                    "pros": pros,
                    "cons": cons,
                    "innovation": 0.5,
                    "feasibility": 0.5,
                    "cross_model_error": str(e),
                    "debate_quality": self._assess_debate_quality(
                        debate_log, idea, final_version, pros, cons
                    ),
                })

        # 评估想法
        evaluated_ideas = self._evaluate_ideas(debated_ideas)

        result = {
            "debate_ideas": evaluated_ideas,
            "final_ideas": [i["final_idea"] for i in evaluated_ideas[:3]],
            "total_ideas_generated": len(ideas),
            "total_ideas_debated": len(debated_ideas),
            # 辩论质量评估（设计文档建议）
            "debate_quality": evaluated_ideas[0].get("debate_quality", "unknown") if evaluated_ideas else "unknown",
            # 跨模型辩论元信息
            "cross_model_meta": {
                "enabled": True,
                "mode": self._cross_model_debater.mode if self._cross_model_debater else "unknown",
                "all_models_used": list(set(
                    m for idea in debated_ideas
                    for m in idea.get("models_used", [])
                )),
                "all_vendors": list(set(
                    v for idea in debated_ideas
                    for v in idea.get("vendors_used", [])
                )),
            },
        }

        # 添加最佳想法的辩论可视化
        if evaluated_ideas:
            top = evaluated_ideas[0]
            if "cross_model_result" in top:
                cm_result = top["cross_model_result"]
                result["debate_visualization"] = {
                    "mode": cm_result.get("mode"),
                    "models_used": cm_result.get("models_used", []),
                    "vendors_used": cm_result.get("vendors_used", []),
                    "dimension_scores": cm_result.get("dimension_scores", {}),
                    "confidence_level": cm_result.get("confidence_level"),
                }
                result["enhanced_conclusion"] = cm_result.get("final_conclusion", "")

        return result

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行辩论

        Returns:
            {
                "debate_ideas": [
                    {
                        "idea": str,
                        "pros": List[str],
                        "cons": List[str],
                        "feasibility": float (0-1),
                        "innovation": float (0-1),
                        "debate_log": List[round_messages]
                    },
                    ...
                ],
                "final_ideas": List[str] - 最终推荐的想法
            }
        """
        # 获取文献分析结果
        analysis = context.get_state("literature_analysis", {})
        concepts = context.get_state("concepts", [])

        if not analysis:
            raise ValueError("No literature analysis found. Run literature_analysis first.")

        logger.info(f"Starting idea debate with {self.debate_rounds} rounds")

        # 初始研究空白和问题
        gaps = analysis.get("analysis", {}).get("gaps", [])
        questions = analysis.get("analysis", {}).get("research_questions", [])

        # 生成初始想法
        initial_ideas = self._generate_initial_ideas(gaps, questions, concepts)

        # ========== 跨模型辩论模式 ==========
        if self.cross_model_enabled and self._cross_model_debater:
            logger.info("Using cross-model debate mode")
            result = self._execute_cross_model_debate(
                initial_ideas[:3],
                analysis,
                context,
            )
            logger.info(f"Cross-model debate complete: {len(result.get('debate_ideas', []))} ideas")
            # Save all results to context for approval gate
            context.set_state("debate_ideas", result.get("debate_ideas", []))
            context.set_state("final_ideas", result.get("final_ideas", []))
            context.set_state("debate_quality", result.get("debate_quality", "unknown"))
            return result
        # ===================================

        # ========== 原生辩论模式 (默认) ==========
        debated_ideas = []
        for idea in initial_ideas[:3]:  # 限制数量
            logger.info(f"Debating idea: {idea[:50]}...")
            debate_log = self._run_debate(idea, analysis)

            # 提取最终版本
            final_version = self._synthesize_final_idea(idea, debate_log)

            pros = self._extract_pros(debate_log)
            cons = self._extract_cons(debate_log)

            # 评估辩论质量
            debate_quality = self._assess_debate_quality(
                debate_log, idea, final_version, pros, cons
            )

            debated_ideas.append({
                "original_idea": idea,
                "debate_log": debate_log,
                "final_idea": final_version,
                "pros": pros,
                "cons": cons,
                "debate_quality": debate_quality,
            })
        
        # 评估想法
        evaluated_ideas = self._evaluate_ideas(debated_ideas)
        
        result = {
            "debate_ideas": evaluated_ideas,
            "final_ideas": [i["final_idea"] for i in evaluated_ideas[:3]],
            "total_ideas_generated": len(initial_ideas),
            "total_ideas_debated": len(debated_ideas),
            # 辩论质量评估（设计文档建议）
            "debate_quality": evaluated_ideas[0].get("debate_quality", "unknown") if evaluated_ideas else "unknown",
        }

        # Run enhanced multi-dimensional debate on the top idea
        if evaluated_ideas:
            top_idea = evaluated_ideas[0]["final_idea"]
            context_summary = self._summarize_analysis(analysis)
            enhanced = self._run_enhanced_debate_sync(top_idea, analysis, context_summary)
            result["debate_visualization"] = enhanced["debate_visualization"]
            result["enhanced_conclusion"] = enhanced["final_conclusion"]
            result["confidence_level"] = enhanced["confidence_level"]

            # Run multi-agent structured debate
            multiagent = self._run_multiagent_debate(top_idea, analysis, context_summary)
            result["multiagent_debate"] = {
                "step_summaries": multiagent.get("step_summaries", []),
                "error": multiagent.get("error"),
            }

        logger.info(f"Idea debate complete: {len(evaluated_ideas)} ideas evaluated")

        # Save all results to context for approval gate
        context.set_state("debate_ideas", evaluated_ideas)
        context.set_state("final_ideas", result["final_ideas"])
        context.set_state("debate_quality", result["debate_quality"])

        return result
    
    def _generate_initial_ideas(self,
                               gaps: List[str],
                               questions: List[str],
                               concepts: List[str]) -> List[str]:
        """生成初始研究想法（并行执行）"""
        prompts = []

        # 基于研究空白生成 (3)
        for gap in gaps[:3]:
            prompts.append((
                "gap",
                f"""
Based on the research gap identified:
"{gap}"

Generate an innovative research idea that addresses this gap.
Consider the following concepts: {', '.join(concepts[:10])}

The idea should be:
- Novel and original
- Technically feasible with current technology
- Potentially high impact
- Clearly defined problem and approach

Provide a concise one-paragraph description of the research idea.
"""
            ))

        # 基于研究问题生成 (2)
        for question in questions[:2]:
            prompts.append((
                "question",
                f"""
Propose a research direction to answer this question:
"{question}"

The proposal should include:
- Specific hypothesis or objective
- Proposed methodology
- Expected outcomes

Keep it concise (one paragraph).
"""
            ))

        def generate_idea(item):
            type_, prompt = item
            try:
                temp = 0.8 if type_ == "gap" else 0.7
                response = self.model_gateway.chat(
                    "innovator",
                    [{"role": "user", "content": prompt}],
                    temperature=temp,
                    max_tokens=300
                )
                return response.strip()
            except Exception as e:
                logger.error(f"Failed to generate idea for {type_}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(generate_idea, prompts))

        return list(set(r for r in results if r))
    
    def _run_debate(self, idea: str, analysis: Dict) -> List[Dict]:
        """运行多轮辩论"""
        debate_log = []
        
        context_summary = self._summarize_analysis(analysis)
        
        for round_num in range(self.debate_rounds):
            logger.debug(f"Debate round {round_num + 1}")

            def get_role_response(role):
                """获取单个角色的响应"""
                prompt = self._build_role_prompt(
                    role=role,
                    idea=idea,
                    context=context_summary,
                    previous_messages=[] if round_num == 0 else []
                )
                try:
                    response = self.model_gateway.chat(
                        role["name"].lower(),
                        [{"role": "user", "content": prompt}],
                        temperature=0.7 if role["name"] == "Innovator" else 0.3,
                        max_tokens=400
                    )
                    return {
                        "role": role["name"],
                        "content": response.strip(),
                        "round": round_num + 1
                    }
                except Exception as e:
                    logger.error(f"Debate round {round_num} failed for {role['name']}: {e}")
                    return {
                        "role": role["name"],
                        "content": f"[Error: {e}]",
                        "round": round_num + 1
                    }

            with ThreadPoolExecutor(max_workers=max(1, len(self.roles))) as executor:
                futures = {executor.submit(get_role_response, role): role for role in self.roles}
                round_messages = []
                for future in as_completed(futures):
                    round_messages.append(future.result())

            debate_log.extend(round_messages)
        
        return debate_log

    def _run_enhanced_debate_sync(
        self,
        idea: str,
        analysis: Dict[str, Any],
        context_summary: str,
    ) -> Dict[str, Any]:
        """Run multi-dimensional debate with cross-examination and visualization (sync version).

        Enhances the standard debate with:
        - 5-dimension scoring (Methodology, Data Support, Generalizability, Innovation, Reproducibility)
        - Cross-examination / rebuttal generation
        - Argument quality evaluation
        - Visualization data (radar chart, timeline)

        Returns:
            {
                "debate_visualization": {...},
                "final_conclusion": str,
                "confidence_level": str,
            }
        """
        from tutor.core.workflow.debate_framework import (
            DimensionType, ArgumentEvaluator,
        )

        # Build positions with initial arguments
        positions = []
        dim_map = {
            "Innovator": DimensionType.INNOVATION,
            "Skeptic": DimensionType.DATA_SUPPORT,
            "Pragmatist": DimensionType.REPRODUCIBILITY,
            "Expert": DimensionType.METHODOLOGY,
        }

        for role_def in self.roles:
            dim = dim_map.get(role_def["name"], DimensionType.INNOVATION)
            pos = DebatePosition(
                position_id=role_def["name"].lower(),
                name=role_def["name"],
                description=role_def["persona"],
            )

            prompt = self._build_role_prompt(
                role=role_def,
                idea=idea,
                context=context_summary,
                previous_messages=[],
            )
            try:
                response = self.model_gateway.chat(
                    role_def["name"].lower(),
                    [{"role": "user", "content": prompt}],
                    temperature=0.7 if role_def["name"] == "Innovator" else 0.3,
                    max_tokens=400,
                )
                arg = Argument(
                    content=response.strip(),
                    source="reasoning",
                    dimension=dim,
                    speaker=role_def["name"],
                    round=1,
                )
                ArgumentEvaluator.evaluate(arg, idea[:100])
                pos.add_argument(arg)
            except Exception as e:
                logger.error(f"Enhanced debate failed for {role_def['name']}: {e}")

            positions.append(pos)

        # Compute dimension scores per position
        for pos in positions:
            pos.compute_dimension_scores()

        # Build radar chart data
        radar = {
            "dimensions": [d.value for d in DimensionType],
            "positions": [],
        }
        for pos in positions:
            radar["positions"].append({
                "name": pos.name,
                "scores": [pos.dimension_scores.get(d, 0.0) for d in DimensionType],
            })

        # Compute quality distribution
        quality_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "invalid": 0}
        for pos in positions:
            for arg in pos.arguments:
                quality_dist[arg.quality.name.lower()] += 1

        # Build timeline (one round per debate_rounds)
        timeline = []
        for round_num in range(1, self.debate_rounds + 1):
            round_scores = {pos.name: pos.dimension_scores.get(
                DimensionType.INNOVATION, 0.0
            ) for pos in positions}
            timeline.append({
                "round": round_num,
                "scores": round_scores,
                "rebuttals": len(positions),
            })

        # Generate conclusion text
        sorted_pos = sorted(positions, key=lambda p: p.overall_score, reverse=True)
        if sorted_pos:
            winner = sorted_pos[0]
            conclusion_lines = [
                f"获胜立场：{winner.name} (评分: {winner.overall_score:.2f})",
                "各维度评分：",
            ]
            for dim, score in winner.dimension_scores.items():
                conclusion_lines.append(f"  - {dim.value}: {score:.2f}")
            conclusion = "\n".join(conclusion_lines)
        else:
            conclusion = "辩论未产生有效结论"

        # Confidence level
        if len(positions) >= 2 and sorted_pos:
            scores = [p.overall_score for p in positions]
            gap = scores[0] - scores[1] if len(scores) > 1 else 0
            confidence = "high" if gap > 0.3 else ("medium" if gap > 0.15 else "low")
        else:
            confidence = "low"

        return {
            "debate_visualization": {
                "radar_chart": radar,
                "timeline": timeline,
                "quality_distribution": quality_dist,
            },
            "final_conclusion": conclusion,
            "confidence_level": confidence,
        }

    def _run_multiagent_debate(
        self,
        idea: str,
        analysis: Dict[str, Any],
        context_summary: str,
    ) -> Dict[str, Any]:
        """Run multi-agent debate using AgentOrchestrator.

        Creates LLMAgent instances for each debate role (Innovator, Skeptic,
        Pragmatist, Expert), registers them with an AgentOrchestrator, and
        runs a structured multi-step debate workflow.

        Returns:
            {
                "multiagent_result": WorkflowResult,
                "debate_messages": List[AgentMessage],
                "step_summaries": [{"step": str, "agent": str, "content": str}, ...],
            }
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        # Lazy import to avoid circular deps
        from tutor.core.multiagent.base import LLMAgent
        from tutor.core.multiagent.orchestrator import AgentOrchestrator

        # Build role prompts
        role_prompts = {}
        for role_def in self.roles:
            role_prompts[role_def["name"].lower()] = {
                "prompt": self._build_role_prompt(
                    role=role_def,
                    idea=idea,
                    context=context_summary,
                    previous_messages=[],
                ),
                "temperature": 0.7 if role_def["name"] == "Innovator" else 0.3,
            }

        # Create agents
        agents = {}
        for role_def in self.roles:
            role_id = role_def["name"].lower()
            prompt_data = role_prompts.get(role_id, {})
            agent = LLMAgent(
                agent_id=role_id,
                name=role_def["name"],
                description=role_def["description"],
                model_gateway=self.model_gateway,
                system_prompt=f"You are {role_def['name']}: {role_def['persona']}\n\nYour goal: {role_def['goal']}",
                model_role=role_id,
                temperature=prompt_data.get("temperature", 0.5),
                max_tokens=400,
            )
            agents[role_id] = agent

        # Build debate steps
        # Step 1: Innovator proposes
        # Step 2: Skeptic critiques
        # Step 3: Pragmatist evaluates feasibility
        # Step 4: Expert contextualizes
        # Step 5: All respond to each other (cross-examination)
        steps = [
            {
                "name": "propose",
                "source": "innovator",
                "targets": ["skeptic", "pragmatist", "expert"],
            },
            {
                "name": "critique",
                "source": "skeptic",
                "targets": ["innovator", "pragmatist"],
            },
            {
                "name": "feasibility",
                "source": "pragmatist",
                "targets": ["innovator", "skeptic"],
            },
            {
                "name": "contextualize",
                "source": "expert",
                "targets": ["innovator", "skeptic", "pragmatist"],
            },
        ]

        # Run async orchestrator in thread pool
        def run_orchestrator():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                orchestrator = AgentOrchestrator(workflow_id=f"debate-{id(idea)}")
                for agent in agents.values():
                    orchestrator.add_agent(agent)
                orchestrator.set_steps(steps)

                result = loop.run_until_complete(
                    orchestrator.run(
                        initial_message=f"Evaluate this research idea: {idea[:200]}",
                        context={"idea": idea, "context": context_summary},
                    )
                )
                return result
            finally:
                loop.close()

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_orchestrator)
                workflow_result = future.result(timeout=60)

            # Extract summaries from messages
            step_summaries = []
            for step in workflow_result.steps:
                step_summaries.append({
                    "step": step.step_name,
                    "agent": step.agent_id,
                    "content": step.response.message.content[:200] if step.response.success else f"[Error: {step.response.error}]",
                })

            return {
                "multiagent_result": workflow_result,
                "debate_messages": workflow_result.final_messages,
                "step_summaries": step_summaries,
            }
        except Exception as e:
            logger.error(f"Multiagent debate failed: {e}")
            return {
                "multiagent_result": None,
                "debate_messages": [],
                "step_summaries": [],
                "error": str(e),
            }

    def _build_role_prompt(self,
                          role: Dict[str, str],
                          idea: str,
                          context: str,
                          previous_messages: List[Dict]) -> str:
        """构建角色发言提示"""
        if previous_messages:
            prev_lines = [m["role"] + ": " + m["content"] for m in previous_messages]
            discussion = "Previous discussion:" + "\n" + "\n".join(prev_lines)
        else:
            discussion = ""

        lines = [
            "You are " + role["name"] + ": " + role["persona"],
            "",
            role["goal"],
            "",
            "Research Context:",
            context,
            "",
            'Current Research Idea:',
            '"' + idea + '"',
            "",
            discussion,
            "",
            "Provide your perspective on this idea. " + ("Focus on strengthening the proposal." if role["name"] == "Pragmatist" else ""),
        ]
        prompt = "\n".join(lines)
        return prompt

    def _summarize_analysis(self, analysis: Dict) -> str:
        """总结分析结果"""
        a = analysis.get("analysis", {})
        summary = f"""
Total Papers: {a.get('total_papers', 0)}
Key Concepts: {', '.join(a.get('key_concepts', [])[:10])}
Research Gaps: {'; '.join(a.get('gaps', [])[:5])}
"""
        return summary.strip()
    
    def _synthesize_final_idea(self, original: str, debate_log: List[Dict]) -> str:
        """综合辩论内容，生成最终想法"""
        prompt = f"""
Original idea:
"{original}"

Debate discussion:
{chr(10).join([f"{m['role']}: {m['content']}" for m in debate_log])}

Based on the discussion, synthesize an improved final version of the research idea.
Incorporate the best points from all perspectives and address the critiques.
Provide a clear, concise, and actionable research proposal (one paragraph).
"""
        
        try:
            response = self.model_gateway.chat(
                "synthesizer",
                [{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=400
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to synthesize idea: {e}")
            return original
    
    def _evaluate_ideas(self, debated_ideas: List[Dict]) -> List[Dict]:
        """评估想法（并行执行）"""
        def evaluate_one(idea_data):
            prompt = f"""
Evaluate this research idea on two dimensions (0-1 scale):

Idea:
{idea_data['final_idea']}

Pros identified:
{chr(10).join([f"- {p}" for p in idea_data.get('pros', [])])}

Cons identified:
{chr(10).join([f"- {c}" for c in idea_data.get('cons', [])])}

Provide scores for:
1. Innovation: (how novel and groundbreaking)
2. Feasibility: (how practical to implement)

Output format: Innovation: <score>, Feasibility: <score>
Example: Innovation: 0.85, Feasibility: 0.65
"""
            try:
                response = self.model_gateway.chat(
                    "evaluator",
                    [{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=100
                )
                innovation, feasibility = self._parse_scores(response)
                idea_data["innovation"] = innovation
                idea_data["feasibility"] = feasibility
            except Exception as e:
                logger.error(f"Failed to evaluate idea: {e}")
                idea_data["innovation"] = 0.5
                idea_data["feasibility"] = 0.5
            return idea_data

        with ThreadPoolExecutor(max_workers=max(1, len(debated_ideas))) as executor:
            evaluated = list(executor.map(evaluate_one, debated_ideas))

        evaluated.sort(key=lambda x: (x["innovation"] + x["feasibility"]) / 2, reverse=True)
        return evaluated
    
    def _parse_scores(self, response: str) -> tuple[float, float]:
        """解析评分"""
        innovation = self._extract_score(response, r'Innovation:\s*([\d.]+)')
        feasibility = self._extract_score(response, r'Feasibility:\s*([\d.]+)')
        return innovation, feasibility

    def _extract_score(self, text: str, pattern: str) -> float:
        """从文本提取评分"""
        import re
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                score = float(match.group(1))
                return max(0, min(1, score))
            except:
                pass
        return 0.5

    def _extract_pros(self, debate_log: List[Dict]) -> List[str]:
        """从辩论日志提取优点"""
        # MVP: 简化提取，实际需要更智能的提取
        pros = []
        for msg in debate_log:
            if msg["role"] in ["Pragmatist", "Expert"]:
                # 提取正面陈述（简化）
                content = msg["content"]
                if "strong" in content.lower() or "good" in content.lower() or "feasible" in content.lower():
                    pros.append(content[:100])
        return pros[:5]
    
    def _extract_cons(self, debate_log: List[Dict]) -> List[str]:
        """从辩论日志提取缺点"""
        cons = []
        for msg in debate_log:
            if msg["role"] == "Skeptic":
                # 提取批评（简化）
                cons.append(msg["content"][:100])
        return cons[:5]

    def _assess_debate_quality(
        self,
        debate_log: List[Dict],
        original_idea: str,
        final_idea: str,
        pros: List[str],
        cons: List[str],
        cross_model_data: Optional[Dict] = None,
    ) -> str:
        """评估辩论质量：genuine_conflict vs weak_conflict vs false_consensus

        根据设计文档，辩论质量评估用于判断：
        - genuine_conflict: 双方真正针锋相对，Skeptic 提出了实质性质疑
        - weak_conflict: 存在一些质疑但不够充分
        - false_consensus: Skeptic 基本上被说服，达成假共识

        Returns:
            "genuine_conflict" | "weak_conflict" | "false_consensus"
        """
        import re

        # 提取 Skeptic 的消息
        skeptic_messages = [m["content"] for m in debate_log if m.get("role") == "Skeptic"]
        skeptic_text = " ".join(skeptic_messages).lower()

        # 质疑关键词（表示真正的批评）
        challenge_patterns = [
            r'\bbut\b', r'\bhowever\b', r'\bproblem\b', r'\bissue\b',
            r'\bflaw\b', r'\brisk\b', r'\bconcern\b', r'\bweakness\b',
            r'\bunlikely\b', r'\boverstated\b', r'\bchallenge\b',
            r'\bcritique\b', r'\bdifficult\b', r'\bfail\b', r'\bdrawback\b',
            r'\blimitations?\b', r'\bnot\s+clear\b', r'\buncertain\b'
        ]

        # 认同关键词（表示基本上同意）
        agreement_patterns = [
            r'\bagree\b', r'\byes\b', r'\bgood\b', r'\bstrong\b',
            r'\bvalid\b', r'\bsound\b', r'\breasonable\b', r'\bexcellent\b',
            r'\bwell\s+designed\b', r'\bconvincing\b', r'\binteresting\b'
        ]

        challenge_count = sum(1 for p in challenge_patterns if re.search(p, skeptic_text))
        agreement_count = sum(1 for p in agreement_patterns if re.search(p, skeptic_text))

        # 检查跨模型数据（如果可用）
        if cross_model_data:
            counter_args = cross_model_data.get("counter_arguments", [])
            key_args = cross_model_data.get("key_arguments", [])
            # 如果没有反论点，说明没有真正辩论
            if not counter_args:
                return "false_consensus"
            # 如果反论点数量明显少于正论点，可能有问题
            if len(counter_args) < len(key_args) / 2:
                return "weak_conflict"
            # 如果有足够多的实质性反论点，说明是真正的辩论
            if len(counter_args) >= 2 and any(len(c) > 50 for c in counter_args):
                return "genuine_conflict"

        # 分析 Skeptic 回复长度
        avg_skeptic_length = sum(len(m) for m in skeptic_messages) / max(len(skeptic_messages), 1)

        # 决策逻辑
        # genuine_conflict: 有足够多的质疑关键词且回复长度足够
        if challenge_count >= 2 and avg_skeptic_length > 100:
            return "genuine_conflict"

        # false_consensus: 没有质疑关键词且有很多认同关键词，或没有任何缺点
        if challenge_count == 0 and agreement_count >= 2:
            return "false_consensus"

        # false_consensus: 没有任何 cons，且 pros 数量很多
        if len(cons) == 0 and len(pros) >= 3:
            return "false_consensus"

        # weak_conflict: 有一些质疑但不够充分
        if challenge_count >= 1 and avg_skeptic_length > 50:
            return "weak_conflict"

        # 如果想法有实质性改变，可能经过了真正的辩论
        if original_idea != final_idea and len(final_idea) < len(original_idea) * 0.8:
            return "genuine_conflict"

        return "weak_conflict"

    def validate(self, context: WorkflowContext) -> List[str]:
        """验证前置条件"""
        errors = []
        
        analysis = context.get_state("literature_analysis", {})
        if not analysis:
            errors.append("No literature analysis found. Run literature_analysis first.")
        
        return errors


class IdeaEvaluationStep(WorkflowStep):
    """想法评估步骤
    
    对最终想法进行更详细的评估：
    - 创新性评分
    - 可行性评分
    - 资源需求估计
    - 风险评估
    - 推荐优先级
    
    输出状态：
    - evaluated_ideas: List[Dict] - 详细评估结果
    - recommended_idea: Dict - 推荐的想法
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="idea_evaluation",
            description="Detailed evaluation of research ideas"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行评估
        
        Returns:
            {
                "evaluated_ideas": [
                    {
                        "idea": str,
                        "scores": {
                            "innovation": float,
                            "feasibility": float,
                            "impact": float,
                            "clarity": float
                        },
                        "resource_requirements": str,
                        "risks": List[str],
                        "mitigation": str
                    },
                    ...
                ],
                "recommended_idea": Dict - 排名第一的想法,
                "evaluation_summary": str - 评估总结
            }
        """
        debate_ideas = context.get_state("debate_ideas", [])
        
        if not debate_ideas:
            raise ValueError("No debated ideas found. Run idea_debate first.")
        
        logger.info(f"Evaluating {len(debate_ideas)} ideas")
        
        evaluated_ideas = []
        
        for idea_data in debate_ideas:
            idea = idea_data["final_idea"]
            
            evaluation = self._evaluate_idea(idea)
            evaluated_ideas.append({
                **idea_data,
                "detailed_evaluation": evaluation
            })
        
        # 综合评分排序
        for idea in evaluated_ideas:
            scores = idea["detailed_evaluation"]["scores"]
            idea["overall_score"] = (
                scores["innovation"] * 0.3 +
                scores["feasibility"] * 0.4 +
                scores["impact"] * 0.2 +
                scores["clarity"] * 0.1
            )
        
        evaluated_ideas.sort(key=lambda x: x["overall_score"], reverse=True)

        # 推荐最佳想法
        recommended = evaluated_ideas[0] if evaluated_ideas else None

        # 计算最弱维度和建议路由（设计文档建议）
        weakest_dimension, routing_decision = self._compute_routing(evaluated_ideas)

        result = {
            "evaluated_ideas": evaluated_ideas,
            "recommended_idea": recommended,
            "evaluation_summary": self._generate_summary(evaluated_ideas),
            # 评分路由决策（设计文档建议）
            "weakest_dimension": weakest_dimension,
            "routing_decision": routing_decision,
        }
        
        logger.info(
            f"Idea evaluation complete. Best idea: "
            f"{recommended['final_idea'][:50] if recommended else 'None'} "
            f"(score: {recommended.get('overall_score', 0):.2f})"
        )
        
        return result
    
    def _evaluate_idea(self, idea: str) -> Dict[str, Any]:
        """评估单个想法"""
        prompt = f"""
Evaluate this research idea comprehensively:

{idea}

Rate each dimension on a scale of 0-1:
1. Innovation: How novel and different from existing work?
2. Feasibility: How practical to implement with available resources?
3. Impact: Potential significance and contribution to the field?
4. Clarity: How well-defined and understandable?

Also provide:
- Resource requirements (time, skills, equipment)
- Top 3 risks or challenges
- Suggested mitigation strategies

Be objective and thorough.
"""
        
        try:
            response = self.model_gateway.chat(
                "evaluator",
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800
            )
            
            # 解析响应
            return self._parse_evaluation(response)
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return {
                "scores": {"innovation": 0.5, "feasibility": 0.5, "impact": 0.5, "clarity": 0.5},
                "resource_requirements": "Unknown",
                "risks": ["Evaluation failed"],
                "mitigation": "Retry evaluation"
            }
    
    def _parse_evaluation(self, response: str) -> Dict[str, Any]:
        """解析评估响应"""
        import re
        
        # 提取评分（简化版）
        innovation = self._extract_score(response, r'Innovation:\s*([\d.]+)')
        feasibility = self._extract_score(response, r'Feasibility:\s*([\d.]+)')
        impact = self._extract_score(response, r'Impact:\s*([\d.]+)')
        clarity = self._extract_score(response, r'Clarity:\s*([\d.]+)')
        
        # 提取资源需求（简化）
        resource_match = re.search(r'Resource requirements:(.+?)(?=\n\n|\nRisks|$)', response, re.DOTALL)
        resource_requirements = resource_match.group(1).strip() if resource_match else "Not specified"
        
        # 提取风险
        risks = []
        risk_section = re.search(r'Top 3 risks:(.+?)(?=\n\n|\nMitigation|$)', response, re.DOTALL)
        if risk_section:
            risks = [r.strip() for r in risk_section.group(1).split('\n') if r.strip()]
        
        # 提取缓解策略
        mitigation_match = re.search(r'mitigation:(.+?)(?=$)', response, re.DOTALL | re.IGNORECASE)
        mitigation = mitigation_match.group(1).strip() if mitigation_match else "Not specified"
        
        return {
            "scores": {
                "innovation": innovation,
                "feasibility": feasibility,
                "impact": impact,
                "clarity": clarity
            },
            "resource_requirements": resource_requirements,
            "risks": risks[:3],
            "mitigation": mitigation
        }
    
    def _extract_score(self, text: str, pattern: str) -> float:
        """从文本提取评分"""
        import re
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                score = float(match.group(1))
                return max(0, min(1, score))
            except:
                pass
        return 0.5
    
    def _generate_summary(self, evaluated_ideas: List[Dict]) -> str:
        """生成评估总结"""
        if not evaluated_ideas:
            return "No ideas were evaluated."
        
        count = len(evaluated_ideas)
        avg_overall = sum(i["overall_score"] for i in evaluated_ideas) / count
        avg_innovation = sum(i["detailed_evaluation"]["scores"]["innovation"] for i in evaluated_ideas) / count
        avg_feasibility = sum(i["detailed_evaluation"]["scores"]["feasibility"] for i in evaluated_ideas) / count
        
        best = evaluated_ideas[0]
        
        summary = f"""
Evaluated {count} research ideas:
- Average overall score: {avg_overall:.2f}
- Average innovation: {avg_innovation:.2f}
- Average feasibility: {avg_feasibility:.2f}

Recommended idea (score {best['overall_score']:.2f}):
{best['final_idea'][:200]}...
"""
        return summary.strip()

    def _compute_routing(self, evaluated_ideas: List[Dict]) -> tuple:
        """根据最弱维度计算路由决策（设计文档建议）

        评分路由逻辑（参照设计文档 Review 路由）:
        - 如果最弱维度是 innovation，且 < 0.5：退回 W1（想法根本性问题）
        - 如果最弱维度是 feasibility 或 clarity：留在 W2 保留想法（实验设计问题）
        - 如果最弱维度是 impact：留在 W2 保留想法

        Returns:
            (weakest_dimension, routing_decision)
        """
        if not evaluated_ideas:
            return "unknown", "proceed"

        best = evaluated_ideas[0]
        scores = best.get("detailed_evaluation", {}).get("scores", {})

        if not scores:
            return "unknown", "proceed"

        # 找到最弱维度
        weakest = min(scores, key=scores.get)
        weakest_score = scores[weakest]

        # 路由决策
        # 创新性不足 (idea问题) -> 退回 W1 重新生成
        if weakest == "innovation" and weakest_score < 0.5:
            routing = "retry_w1_new_ideas"
            reason = f"Innovation score ({weakest_score:.2f}) is too low, fundamental idea change needed"
        # 可行性或清晰度问题 -> 留在 W2 改进实验设计
        elif weakest in ("feasibility", "clarity"):
            routing = "proceed_w2_keep_idea"
            reason = f"{weakest.capitalize()} score ({weakest_score:.2f}) could be improved, proceed with experiment"
        # 影响不足 -> 留在 W2
        elif weakest == "impact":
            routing = "proceed_w2_keep_idea"
            reason = f"Impact score ({weakest_score:.2f}) could be stronger, proceed with experiment"
        else:
            routing = "proceed"
            reason = "All dimensions acceptable"

        logger.info(f"Routing decision: weakest={weakest} ({weakest_score:.2f}), routing={routing}")

        return weakest, routing

    def validate(self, context: WorkflowContext) -> List[str]:
        """验证前置条件"""
        errors = []
        debate_ideas = context.get_state("debate_ideas", [])
        
        if not debate_ideas:
            errors.append("No debated ideas found. Run idea_debate first.")
        
        return errors


class IdeaApprovalGateStep(WorkflowStep):
    """想法审批门控步骤（设计文档介入点 #1）

    在辩论结束后暂停工作流，等待用户审批。
    用户可以：
    - 批准当前想法，进入评估阶段
    - 要求重新生成想法
    - 修改想法后继续

    这个门控是可选的，由配置控制是否启用。
    """

    def __init__(
        self,
        project_id: str = "default",
        required_approval: bool = True,
    ):
        """初始化审批门控

        Args:
            project_id: 项目 ID
            required_approval: 是否需要审批，False 则自动批准
        """
        super().__init__(
            name="idea_approval_gate",
            description="Gate for user approval of debated ideas (Intervention Point #1)"
        )
        self.project_id = project_id
        self.required_approval = required_approval

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行审批门控

        Returns:
            {
                "approval_status": "approved" | "rejected" | "pending",
                "debate_ideas": List[Dict] - 辩论产生的想法,
                "debate_quality": str - 辩论质量评估,
            }

        Raises:
            WorkflowPauseError: 需要暂停等待用户审批
        """
        from .base import WorkflowPauseError

        # 获取辩论结果
        debate_ideas = context.get_state("debate_ideas", [])
        debate_quality = context.get_state("debate_quality", "unknown")
        final_ideas = context.get_state("final_ideas", [])

        # 如果不需要审批或没有想法，自动批准
        if not self.required_approval:
            logger.info("Approval not required, auto-approving ideas")
            return {
                "approval_status": "auto_approved",
                "debate_ideas": debate_ideas,
                "debate_quality": debate_quality,
                "final_ideas": final_ideas,
            }

        # 构建审批数据
        approval_data = {
            "debate_ideas": debate_ideas,
            "debate_quality": debate_quality,
            "final_ideas": final_ideas,
            "total_ideas": len(debate_ideas),
        }

        # 创建审批请求 ID - 使用 workflow_id 确保唯一性
        approval_id = f"{context.workflow_id}_idea_approval"

        # 检查是否已有审批结果
        from .project_gate import get_approval_manager
        manager = get_approval_manager()
        existing = manager.get_request(approval_id)

        if existing and existing.status.value in ("approved", "rejected"):
            # 已有审批结果
            logger.info(f"Idea approval already resolved: {existing.status.value}")
            return {
                "approval_status": existing.status.value,
                "debate_ideas": debate_ideas,
                "debate_quality": debate_quality,
                "final_ideas": final_ideas,
            }

        # 创建新审批请求
        if not existing:
            manager.create_request(
                approval_id=approval_id,
                run_id=context.workflow_id,
                title="审批辩论产生的想法",
                description=f"辩论产生 {len(debate_ideas)} 个想法，辩论质量: {debate_quality}",
                context_data=approval_data,
                timeout_seconds=86400,
            )
            logger.info(f"Created idea approval request: {approval_id}")

        # 保存检查点
        context.save_checkpoint(
            step=context._current_step,
            step_name=self.name,
            input_data=approval_data,
            output_data={"approval_id": approval_id, "waiting_for": "idea_approval"},
        )

        # 抛出暂停异常
        raise WorkflowPauseError(
            f"Workflow paused at idea_approval_gate, waiting for user approval: {approval_id}"
        )

    def validate(self, context: WorkflowContext) -> List[str]:
        """验证前置条件"""
        errors = []
        debate_ideas = context.get_state("debate_ideas", [])

        if not debate_ideas:
            errors.append("No debated ideas found. Run idea_debate first.")

        return errors


class FinalProposalStep(WorkflowStep):
    """最终提案步骤
    
    整合所有信息，生成完整的研究提案文档。
    
    输出：
    - final_proposal: str - Markdown格式的提案
    - proposal_metadata: Dict - 提案元数据
    """
    
    def __init__(self):
        super().__init__(
            name="final_proposal",
            description="Generate final research proposal document"
        )
    
    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """生成最终提案
        
        Returns:
            {
                "final_proposal": str (Markdown),
                "proposal_metadata": Dict,
                "output_files": List[str]  # 生成的文件路径
            }
        """
        # 收集所有需要的信息
        papers = context.get_state("validated_papers", [])
        analysis = context.get_state("literature_analysis", {})
        recommended_idea = context.get_state("recommended_idea", {})
        
        if not recommended_idea:
            raise ValueError("No recommended idea found. Run idea_evaluation first.")
        
        logger.info("Generating final research proposal")
        
        # 构建提案内容
        proposal = self._build_proposal(papers, analysis, recommended_idea)
        
        # 保存提案文件
        output_dir = context.results_dir / "proposal"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        proposal_file = output_dir / "research_proposal.md"
        with open(proposal_file, 'w', encoding='utf-8') as f:
            f.write(proposal)
        
        logger.info(f"Proposal saved to: {proposal_file}")
        
        metadata = {
            "workflow_id": context.workflow_id,
            "generated_at": context.workflow_id,
            "paper_count": len(papers),
            "idea_score": recommended_idea.get("overall_score", 0)
        }
        
        result = {
            "final_proposal": proposal,
            "proposal_metadata": metadata,
            "output_files": [str(proposal_file)]
        }
        
        logger.info("Final proposal generation complete")
        
        return result
    
    def _build_proposal(self, 
                       papers: List,
                       analysis: Dict,
                       idea: Dict) -> str:
        """构建提案文档"""
        idea_title = idea["final_idea"][:100]
        
        proposal = f"""# Research Proposal

## 1. Proposed Research Idea

{idea_title}

**Overall Score:** {idea.get('overall_score', 0):.2f}

### Detailed Description
{idea['final_idea']}

## 2. Innovation and Feasibility

- **Innovation Score:** {idea['detailed_evaluation']['scores']['innovation']:.2f}
- **Feasibility Score:** {idea['detailed_evaluation']['scores']['feasibility']:.2f}
- **Impact Score:** {idea['detailed_evaluation']['scores']['impact']:.2f}
- **Clarity Score:** {idea['detailed_evaluation']['scores']['clarity']:.2f}

## 3. Background and Motivation

### Related Work
This research builds upon {len(papers)} papers that were analyzed:

{chr(10).join([f"- {p.title}" for p in papers[:5]])}

{f"...and {len(papers) - 5} more papers" if len(papers) > 5 else ""}

### Research Gap
Based on literature analysis, the key research gaps identified were:
{chr(10).join([f"- {gap}" for gap in analysis.get('analysis', {}).get('gaps', [])[:3]])}

## 4. Proposed Methodology

{idea['detailed_evaluation'].get('resource_requirements', 'To be determined')}

## 5. Risks and Mitigations

{chr(10).join([f"- **{i+1}.** {risk}" for i, risk in enumerate(idea['detailed_evaluation'].get('risks', [])[:3])])}

Mitigation: {idea['detailed_evaluation'].get('mitigation', 'N/A')}

## 6. Expected Outcomes

- Novel contribution to the field
- Publication in relevant venue
- Open-source implementation if applicable

---

*Generated by TutorClaw IdeaFlow*  
*Workflow ID: {context.workflow_id}*
"""
        return proposal
    
    def validate(self, context: WorkflowContext) -> List[str]:
        """验证前置条件"""
        errors = []
        idea = context.get_state("recommended_idea", {})
        
        if not idea:
            errors.append("No recommended idea found. Run idea_evaluation first.")
        
        return errors


class IdeaFlow(Workflow):
    """IdeaFlow - 研究想法生成工作流

    完整的研究想法生成流程，包含设计文档建议的介入点：
    - 介入点 #1: idea_approval_gate - 辩论结束后用户审批想法
    - 最终项目门控 - 项目完成前用户审批

    流程:
    1. PaperLoadingStep - 加载论文
    2. PaperValidationStep - 验证论文质量
    3. ZoteroLiteratureStep - 补充文献（可选）
    4. LiteratureAnalysisStep - 分析文献
    5. IdeaDebateStep - 辩论生成想法
    6. IdeaApprovalGateStep - [介入点 #1] 用户审批想法
    7. IdeaEvaluationStep - 评估想法
    8. FinalProposalStep - 生成最终提案
    9. ProjectGateStep - [最终审批] 用户审批提案
    """

    def build_steps(self) -> List[WorkflowStep]:
        """构建工作流步骤"""
        project_id = self.config.get("project_id", "unknown")
        # 是否在辩论后需要用户审批（设计文档建议开启）
        require_idea_approval = self.config.get("require_idea_approval", True)

        steps = [
            # 智能输入处理 - 自动识别关键词、arXiv ID、本地文件
            SmartInputStep(auto_search=True, max_auto_papers=5),
            # 自动搜索补充文献
            AutoArxivSearchStep(max_results=5),
            # 加载论文
            PaperLoadingStep(),
            # 验证论文质量
            PaperValidationStep(min_text_length=500, require_abstract=False),
            # 补充 Zotero 文献（可选）
            ZoteroLiteratureStep(),
            # 文献分析
            LiteratureAnalysisStep(self.model_gateway),
            # 辩论生成想法
            IdeaDebateStep(self.model_gateway, self.config),
            # 介入点 #1: 辩论后审批门控（设计文档建议）
            IdeaApprovalGateStep(
                project_id=project_id,
                required_approval=require_idea_approval,
            ),
            IdeaEvaluationStep(self.model_gateway),
            FinalProposalStep(),
            # 最终审批门控 - 暂停等待用户审批想法
            ProjectGateStep(
                project_id=project_id,
                phase="idea",
                title="审批创意生成结果",
                description="请审批生成的研究想法，批准后将启动实验流程"
            ),
        ]
        return steps


__all__ = [
    'IdeaFlow',
    'PaperLoadingStep',
    'PaperValidationStep',
    'LiteratureAnalysisStep',
    'IdeaDebateStep',
    'IdeaApprovalGateStep',
    'IdeaEvaluationStep',
    'FinalProposalStep',
]