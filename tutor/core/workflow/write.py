"""WriteFlow - 论文撰写工作流

根据确定的paper内容和实验结果，自动生成符合学术规范的论文初稿。

MVP限制：
- 仅支持 Markdown 输出
- 不包含 LaTeX 格式检查
- 不支持自动查重
- 专家审核仅作为可选步骤
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from tutor.core.workflow import Workflow, WorkflowStep
from tutor.core.model import ModelGateway
from tutor.core.storage import StorageManager

logger = logging.getLogger(__name__)


class OutlineGenerationStep(WorkflowStep):
    """大纲生成步骤
    
    基于论文主题和实验内容生成论文结构。
    
    输出状态：
    - outline: Dict - 论文大纲（章节结构）
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="outline_generation",
            description="Generate paper outline based on topic and results"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """生成论文大纲"""
        topic = context.get_state("topic", "")
        description = context.get_state("description", "")
        experiment_summary = context.get_state("experiment_summary", {})
        target_format = context.config.get("output_format", "markdown")
        
        logger.info(f"Generating outline for topic: {topic}")
        
        prompt = f"""
Create a detailed outline for a research paper based on the following information.

**Research Topic:**
{topic}

**Research Description:**
{description}

**Experiment Summary:**
- Title: {experiment_summary.get('title', 'N/A')}
- Key Metrics: {experiment_summary.get('metrics', {})}
- Conclusion: {experiment_summary.get('conclusion', 'N/A')}

**Target Format:** {target_format}

Please provide a standard IMRaD (Introduction, Methods, Results, and Discussion) structure with the following sections:
1. Title
2. Abstract (200-300 words)
3. Introduction
   - Background
   - Problem Statement
   - Contributions
4. Related Work (optional)
5. Methodology
   - Approach/Algorithm
   - Experimental Setup
6. Experiments
   - Datasets
   - Baselines
   - Results (with placeholders for figures/tables)
7. Discussion
   - Interpretation
   - Limitations
8. Conclusion
9. References (placeholder)

For each section, provide:
- Section title
- Brief description of content (2-3 sentences)
- Key points to cover

Output format: Markdown with clear headings.
"""
        
        try:
            response = self.model_gateway.chat(
                "writer",
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=1500
            )
            
            outline_text = response.strip()
            
            result = {
                "outline_text": outline_text,
                "outline": self._parse_outline(outline_text),
                "sections": self._extract_sections(outline_text)
            }
            
            logger.info(f"Outline generated: {len(result['sections'])} sections")
            
            return result
            
        except Exception as e:
            logger.error(f"Outline generation failed: {e}")
            raise
    
    def _parse_outline(self, outline_text: str) -> Dict[str, Any]:
        """解析大纲文本（简化版）"""
        lines = outline_text.split('\n')
        sections = []
        current_section = None
        
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    "level": 1,
                    "title": line[2:],
                    "content": ""
                }
            elif line.startswith('## '):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    "level": 2,
                    "title": line[3:],
                    "content": ""
                }
            elif line.startswith('### '):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    "level": 3,
                    "title": line[4:],
                    "content": ""
                }
            elif current_section:
                current_section["content"] += line + "\n"
        
        if current_section:
            sections.append(current_section)
        
        return {"sections": sections}
    
    def _extract_sections(self, outline_text: str) -> List[str]:
        """提取所有章节标题"""
        import re
        sections = []
        for line in outline_text.split('\n'):
            match = re.match(r'^(#{1,3})\s+(.+)$', line)
            if match:
                sections.append(match.group(2).strip())
        return sections
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        if not context.get_state("topic"):
            errors.append("No topic found. Please provide a research topic.")
        return errors


class DraftWritingStep(WorkflowStep):
    """初稿撰写步骤
    
    按章节自动生成内容，包括引用、公式、图表说明。
    
    输出状态：
    - draft_sections: Dict - 各章节草稿
    - draft_complete: bool - 草稿是否完成
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="draft_writing",
            description="Write paper draft section by section"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """撰写论文草稿"""
        outline = context.get_state("outline", {})
        experiment_report = context.get_state("experiment_report", {})
        paper_content = context.get_state("paper_content", {})
        
        logger.info("Starting draft writing...")
        
        sections_data = outline.get("sections", [])
        if not sections_data:
            raise ValueError("No outline found. Run outline_generation first.")
        
        drafts = {}
        
        # 逐章节生成
        for section in sections_data:
            section_title = section["title"]
            section_level = section["level"]
            
            # 跳过低层级子标题（只写主要章节）
            if section_level > 2:
                continue
            
            logger.info(f"Writing section: {section_title}")
            
            section_draft = self._write_section(
                title=section_title,
                description=section.get("content", ""),
                outline=outline,
                experiment_report=experiment_report,
                paper_content=paper_content,
                previous_sections=drafts
            )
            
            drafts[section_title] = {
                "content": section_draft,
                "level": section_level,
                "word_count": len(section_draft.split())
            }
        
        result = {
            "draft_sections": drafts,
            "draft_complete": True,
            "total_sections": len(drafts),
            "total_words": sum(d["word_count"] for d in drafts.values())
        }
        
        logger.info(f"Draft writing complete: {result['total_sections']} sections, {result['total_words']} words")
        
        return result
    
    def _write_section(self,
                      title: str,
                      description: str,
                      outline: Dict,
                      experiment_report: Dict,
                      paper_content: Dict,
                      previous_sections: Dict) -> str:
        """撰写单个章节"""
        
        # 构建上下文信息
        experiment_summary = experiment_report.get("final_report", "")[:1000] if experiment_report else "No experiment report available"
        
        # 之前章节的内容（作为连贯性参考）
        prev_content = ""
        for sec_title, sec_data in list(previous_sections.items())[-2:]:  # 最近2章
            prev_content += f"\n{sec_title}:\n{sec_data['content'][:500]}...\n"
        
        prompt = f"""
Write the "{title}" section of a research paper.

**Section Description from Outline:**
{description}

**Context from Previous Sections:**
{prev_content if prev_content else "This is the first section."}

**Experiment Report Summary:**
{experiment_summary}

**Instructions:**
- Write in formal academic style
- Include appropriate citations (use [Author, Year] format)
- Incorporate relevant experimental results and figures
- Ensure logical flow and coherence with previous sections
- Be specific and evidence-based
- Target length: 300-500 words

Write the complete section content now.
"""
        
        try:
            response = self.model_gateway.chat(
                "writer",
                [{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=1200
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Failed to write section '{title}': {e}")
            return f"[Error: Failed to generate content for {title}: {e}]"
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        if not context.get_state("outline"):
            errors.append("No outline found. Run outline_generation first.")
        return errors


class FormatCheckStep(WorkflowStep):
    """格式检查步骤
    
    检查Markdown格式规范（MVP跳过核心检查，仅做基础验证）。
    
    输出状态：
    - format_issues: List[str] - 格式问题列表
    - format_score: float - 格式评分
    """
    
    def __init__(self):
        super().__init__(
            name="format_check",
            description="Basic format validation (MVP: minimal checks)"
        )
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行格式检查"""
        drafts = context.get_state("draft_sections", {})
        
        logger.info("Running format check...")
        
        issues = []
        score = 1.0
        
        # 检查必需的章节
        required_sections = ["Title", "Abstract", "Introduction", "Methodology", "Experiments", "Conclusion"]
        present_sections = list(drafts.keys())
        
        for req in required_sections:
            if not any(req.lower() in s.lower() for s in present_sections):
                issues.append(f"Missing required section: {req}")
                score -= 0.2
        
        # 检查篇幅（简化）
        total_words = sum(d.get("word_count", 0) for d in drafts.values())
        if total_words < 1500:
            issues.append(f"Paper too short: {total_words} words (expected >= 1500)")
            score -= 0.3
        elif total_words > 10000:
            issues.append(f"Paper too long: {total_words} words (expected <= 10000)")
            score -= 0.1
        
        result = {
            "format_issues": issues,
            "format_score": max(0, score),
            "total_words": total_words,
            "sections_present": present_sections
        }
        
        logger.info(f"Format check complete: score={score:.2f}, issues={len(issues)}")
        
        return result
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        errors = []
        if not context.get_state("draft_sections"):
            errors.append("No draft_sections found. Run draft_writing first.")
        return errors


class ExpertReviewStep(WorkflowStep):
    """专家审核步骤（可选）
    
    对各章节由专家角色评审（MVP作为可选步骤）。
    
    输出状态：
    - expert_feedback: Dict - 专家反馈
    - revision_suggestions: List[str] - 修改建议
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="expert_review",
            description="Optional expert review of draft sections"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行专家审核"""
        drafts = context.get_state("draft_sections", {})
        topic = context.get_state("topic", "")
        
        logger.info("Starting expert review...")
        
        feedback = {}
        revision_suggestions = []
        
        # 对每个主要章节进行审核
        for section_title, section_data in drafts.items():
            logger.debug(f"Reviewing section: {section_title}")
            
            section_feedback = self._review_section(
                title=section_title,
                content=section_data["content"],
                topic=topic
            )
            
            feedback[section_title] = section_feedback
            
            # 提取修改建议
            if "suggestions" in section_feedback:
                revision_suggestions.extend([
                    f"{section_title}: {s}" for s in section_feedback["suggestions"]
                ])
        
        result = {
            "expert_feedback": feedback,
            "revision_suggestions": revision_suggestions,
            "sections_reviewed": len(feedback)
        }
        
        logger.info(f"Expert review complete: {len(feedback)} sections reviewed")
        
        return result
    
    def _review_section(self, title: str, content: str, topic: str) -> Dict[str, Any]:
        """审核单个章节"""
        prompt = f"""
Review this section of a research paper on "{topic}".

**Section:** {title}

**Content:**
{content}

Please provide feedback on:
1. **Clarity**: Is the writing clear and understandable?
2. **Completeness**: Does it cover all necessary points?
3. **Technical Accuracy**: Any errors or inconsistencies?
4. **Flow**: Does it fit logically in the paper structure?
5. **Suggestions**: Specific improvements (list 2-3)

Return as JSON-like format:
Clarity: [score 1-5]
Completeness: [score 1-5]
Technical Accuracy: [score 1-5]
Flow: [score 1-5]
Suggestions: [list of strings]
Overall: [summary]
"""
        
        try:
            response = self.model_gateway.chat(
                "expert",
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600
            )
            
            # 简单解析（实际可能需要更复杂的解析）
            lines = response.strip().split('\n')
            feedback = {
                "raw": response,
                "suggestions": []
            }
            
            for line in lines:
                if line.startswith("Suggestions:") or "suggestion" in line.lower():
                    # 提取建议列表（简化）
                    feedback["suggestions"] = [line.split(":",1)[1].strip()] if ":" in line else [line.strip()]
            
            return feedback
            
        except Exception as e:
            logger.error(f"Section review failed for {title}: {e}")
            return {"error": str(e), "suggestions": []}
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        errors = []
        if not context.get_state("draft_sections"):
            errors.append("No draft_sections found. Run draft_writing first.")
        return errors


class PolishingStep(WorkflowStep):
    """语言润色步骤
    
    语法检查、用词优化、表达改进。
    
    输出状态：
    - polished_sections: Dict - 润色后的章节
    - polish_changes: Dict - 修改统计
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="polishing",
            description="Language polishing and grammar improvement"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行语言润色"""
        drafts = context.get_state("draft_sections", {})
        
        logger.info("Starting language polishing...")
        
        polished = {}
        polish_changes = {}
        
        for section_title, section_data in drafts.items():
            logger.debug(f"Polishing section: {section_title}")
            
            original = section_data["content"]
            
            try:
                polished_content = self._polish_text(original)
                
                # 计算修改统计
                changes = self._count_changes(original, polished_content)
                
                polished[section_title] = {
                    "content": polished_content,
                    "word_count": len(polished_content.split())
                }
                
                polish_changes[section_title] = changes
                
            except Exception as e:
                logger.error(f"Polishing failed for {section_title}: {e}")
                polished[section_title] = section_data  # 保持原样
                polish_changes[section_title] = {"error": str(e)}
        
        result = {
            "polished_sections": polished,
            "polish_changes": polish_changes,
            "sections_polished": len(polished)
        }
        
        logger.info(f"Polishing complete: {len(polished)} sections")
        
        return result
    
    def _polish_text(self, text: str) -> str:
        """润色文本"""
        prompt = f"""
Polish the following academic text for grammar, clarity, and style.

**Requirements:**
- Fix grammar and punctuation errors
- Improve word choice and sentence structure
- Ensure academic tone
- Maintain original meaning and technical content
- Do not add new content or change technical terms

**Original Text:**
{text}

Return the polished version.
"""
        
        try:
            response = self.model_gateway.chat(
                "writer",
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=len(text.split()) * 2  # 大致估算
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Polishing failed: {e}")
            return text  # 返回原文
    
    def _count_changes(self, original: str, polished: str) -> Dict[str, Any]:
        """统计修改量"""
        orig_words = original.split()
        poly_words = polished.split()
        
        return {
            "original_words": len(orig_words),
            "polished_words": len(poly_words),
            "word_diff": len(poly_words) - len(orig_words)
        }
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        errors = []
        if not context.get_state("draft_sections"):
            errors.append("No draft_sections found. Run draft_writing first.")
        return errors


class FinalExportStep(WorkflowStep):
    """最终导出步骤
    
    整合所有内容，生成完整论文文档。
    
    输出：
    - final_paper: str - 完整Markdown论文
    - export_files: List[str] - 导出的文件列表
    """
    
    def __init__(self):
        super().__init__(
            name="final_export",
            description="Assemble and export final paper document"
        )
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行最终导出"""
        outline = context.get_state("outline", {})
        polished_sections = context.get_state("polished_sections", {})
        expert_feedback = context.get_state("expert_feedback", {})
        
        logger.info("Generating final paper...")
        
        # 构建完整论文
        paper_parts = []
        
        # 标题（从outline中找到Title部分）
        title_section = self._find_section(outline, "title")
        if title_section:
            paper_parts.append(f"# {title_section.get('content', 'Untitled').strip()}")
        else:
            paper_parts.append("# Untitled Paper")
        
        # 添加摘要、引言等主要章节
        for section_title, section_data in polished_sections.items():
            # 确定标题级别（默认为##）
            level = section_data.get("level", 2)
            prefix = "#" * level
            
            paper_parts.append(f"\n{prefix} {section_title}\n")
            paper_parts.append(section_data["content"])
        
        # 添加专家反馈摘要（如果有）
        if expert_feedback:
            paper_parts.append("\n## Appendix: Expert Review Notes\n")
            for sec, feedback in expert_feedback.items():
                paper_parts.append(f"\n### {sec}\n")
                paper_parts.append(feedback.get("raw", "No feedback"))
        
        final_paper = "\n".join(paper_parts)
        
        # 保存文件
        output_dir = context.results_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        paper_file = output_dir / "final_paper.md"
        with open(paper_file, 'w', encoding='utf-8') as f:
            f.write(final_paper)
        
        # 导出为纯文本摘要
        summary_file = output_dir / "paper_summary.txt"
        summary = self._generate_summary(polished_sections, expert_feedback)
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        result = {
            "final_paper": final_paper,
            "paper_file": str(paper_file),
            "export_files": [str(paper_file), str(summary_file)],
            "total_words": sum(d.get("word_count", 0) for d in polished_sections.values())
        }
        
        logger.info(f"Final paper exported: {paper_file} ({result['total_words']} words)")
        
        return result
    
    def _find_section(self, outline: Dict, section_name: str) -> Optional[Dict]:
        """在大纲中查找指定章节"""
        sections = outline.get("sections", [])
        for sec in sections:
            if section_name.lower() in sec.get("title", "").lower():
                return sec
        return None
    
    def _generate_summary(self, polished_sections: Dict, expert_feedback: Dict) -> str:
        """生成论文摘要"""
        summary_lines = [
            "WriteFlow Execution Summary",
            "=" * 40,
            f"Total Sections: {len(polished_sections)}",
            f"Total Words: {sum(d.get('word_count', 0) for d in polished_sections.values())}",
            "\nSections:",
        ]
        
        for title, data in polished_sections.items():
            summary_lines.append(f"  - {title} ({data.get('word_count', 0)} words)")
        
        if expert_feedback:
            summary_lines.append(f"\nExpert Review: {len(expert_feedback)} sections reviewed")
            summary_lines.append("Suggestions:")
            for sec, fb in expert_feedback.items():
                suggestions = fb.get("suggestions", [])
                if suggestions:
                    for s in suggestions[:2]:  # 每个章节最多2条
                        summary_lines.append(f"  - {sec}: {s}")
        
        return "\n".join(summary_lines)
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        errors = []
        if not context.get_state("polished_sections"):
            errors.append("No polished_sections found. Run polishing first.")
        return errors


class WriteFlow(Workflow):
    """WriteFlow - 论文撰写工作流
    
    完整工作流：
    1. 大纲生成 → 2. 初稿撰写 → 3. 格式检查 → 4. 专家审核（可选）→ 5. 语言润色 → 6. 最终导出
    
    配置示例：
    ```yaml
    workflow:
      writing:
        output_format: "markdown"
        auto_format_check: true
        expert_review: false  # MVP默认关闭
    ```
    """
    
    def build_steps(self) -> List[WorkflowStep]:
        """构建工作流步骤"""
        steps = [
            OutlineGenerationStep(self.model_gateway),
            DraftWritingStep(self.model_gateway),
            FormatCheckStep(),
        ]
        
        # MVP中专家审核可选
        if self.config.get("expert_review", False):
            steps.append(ExpertReviewStep(self.model_gateway))
        
        steps.extend([
            PolishingStep(self.model_gateway),
            FinalExportStep(),
        ])
        
        return steps


__all__ = [
    'WriteFlow',
    'OutlineGenerationStep',
    'DraftWritingStep',
    'FormatCheckStep',
    'ExpertReviewStep',
    'PolishingStep',
    'FinalExportStep',
]
