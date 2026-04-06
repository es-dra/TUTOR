"""LaTeXFlow - LaTeX论文生成与编译工作流

基于WriteFlow的内容生成LaTeX源码，支持自动编译为PDF。

工作流：
1. 大纲生成（复用WriteFlow）
2. 草稿撰写（复用WriteFlow）
3. LaTeX模板渲染
4. BibTeX引用处理
5. LaTeX编译（pdflatex + bibtex）
6. PDF输出验证

使用方式：
    from core.workflow.latex import LaTeXFlow
    flow = LaTeXFlow(model_gateway, config)
    result = flow.run(topic="...", description="...")
"""

import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from tutor.core.workflow import Workflow, WorkflowStep
from tutor.core.model import ModelGateway
from tutor.core.workflow.write import (
    OutlineGenerationStep,
    DraftWritingStep,
    PolishingStep,
)

logger = logging.getLogger(__name__)


# --- LaTeX模板 ---

DEFAULT_LATEX_TEMPLATE = r"""\documentclass[11pt,a4paper]{article}

% === Packages ===
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{url}
\usepackage{cite}
\usepackage{algorithm}
\usepackage{algorithmic}
\usepackage{subcaption}
\usepackage{xcolor}

% === Layout ===
\usepackage[margin=2.5cm]{geometry}
\setlength{\parindent}{0.5cm}
\setlength{\parskip}{0.2cm}

% === Metadata (auto-filled) ===
\title{TUTOR_TITLE}
\author{TUTOR_AUTHORS}
\date{TUTOR_DATE}

\begin{document}

\maketitle

\begin{abstract}
TUTOR_ABSTRACT
\end{abstract}

TUTOR_BODY

% === References ===
\bibliographystyle{plain}
\bibliography{references}

\end{document}
"""

SECTION_TEMPLATE = {
    "section": r"\section{SECTION_TITLE}",
    "subsection": r"\subsection{SECTION_TITLE}",
    "subsubsection": r"\subsubsection{SECTION_TITLE}",
}


class LaTeXRenderStep(WorkflowStep):
    """LaTeX源码渲染步骤

    将Markdown格式的草稿内容转换为LaTeX源码。
    """

    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="latex_render",
            description="Render Markdown draft to LaTeX source"
        )
        self.model_gateway = model_gateway

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        outline = context.get_state("outline", {})
        polished_sections = context.get_state("polished_sections", {})
        config = context.config.get("latex", {})

        title = self._extract_title(outline)
        authors = config.get("authors", "Anonymous")
        date_str = datetime.now(timezone.utc).strftime("%B %Y")
        # 首先从大纲中提取摘要
        abstract_text = self._extract_abstract(outline)
        # 如果大纲中没有摘要，从polished_sections中获取
        if not abstract_text:
            abstract_text = self._get_section_content(polished_sections, "Abstract")
        # 如果还是没有摘要，生成一个默认摘要
        if not abstract_text:
            abstract_text = "This paper presents a novel approach to solve a significant problem in the field."

        # Render body sections
        body_parts = []
        for section_title, section_data in polished_sections.items():
            if section_title.lower() in ("abstract", "title"):
                continue

            level = section_data.get("level", 2)
            if level == 2:
                latex_heading = SECTION_TEMPLATE["section"].replace("SECTION_TITLE", section_title)
            elif level == 3:
                latex_heading = SECTION_TEMPLATE["subsection"].replace("SECTION_TITLE", section_title)
            else:
                latex_heading = SECTION_TEMPLATE["subsubsection"].replace("SECTION_TITLE", section_title)

            latex_content = self._markdown_to_latex(section_data.get("content", ""))
            body_parts.append(f"{latex_heading}\n\n{latex_content}")

        # Fill template
        latex_source = DEFAULT_LATEX_TEMPLATE
        latex_source = latex_source.replace("TUTOR_TITLE", title)
        latex_source = latex_source.replace("TUTOR_AUTHORS", authors)
        latex_source = latex_source.replace("TUTOR_DATE", date_str)
        latex_source = latex_source.replace("TUTOR_ABSTRACT", abstract_text)
        latex_source = latex_source.replace("TUTOR_BODY", "\n\n".join(body_parts))

        # Apply LaTeX-specific formatting rules
        latex_source = self._clean_latex(latex_source)

        # Save .tex file
        output_dir = context.results_dir / "latex"
        output_dir.mkdir(parents=True, exist_ok=True)

        tex_file = output_dir / "paper.tex"
        tex_file.write_text(latex_source, encoding="utf-8")

        # Create empty .bib if not exists
        bib_file = output_dir / "references.bib"
        if not bib_file.exists():
            bib_file.write_text("% References\n", encoding="utf-8")

        logger.info(f"LaTeX source rendered: {tex_file}")
        return {
            "latex_source": latex_source,
            "tex_file": str(tex_file),
            "bib_file": str(bib_file),
            "section_count": len(body_parts),
        }

    def _extract_title(self, outline: Dict) -> str:
        for sec in outline.get("sections", []):
            if "title" in sec.get("title", "").lower():
                return sec.get("content", "Untitled Paper").strip()
        return "Untitled Paper"

    def _extract_abstract(self, outline: Dict) -> str:
        """从大纲中提取摘要内容"""
        for sec in outline.get("sections", []):
            if "abstract" in sec.get("title", "").lower():
                return sec.get("content", "").strip()
        # 如果在大纲中找不到摘要，尝试从polished_sections中获取
        return ""

    def _get_section_content(self, sections: Dict, name: str) -> str:
        for key, data in sections.items():
            if key.lower() == name.lower():
                return data.get("content", "")
        return ""

    def _markdown_to_latex(self, md_text: str) -> str:
        """基本Markdown → LaTeX转换"""
        text = md_text

        # 移除开头的标题（避免与LaTeX section重复）
        text = re.sub(r'^#{1,3}\s+.+?\n+', '', text, flags=re.MULTILINE)

        # Code blocks
        text = re.sub(
            r"```(\w*)\n(.*?)```",
            lambda m: r"\begin{verbatim}" + "\n" + m.group(2) + r"\end{verbatim}",
            text,
            flags=re.DOTALL,
        )

        # Inline code
        text = re.sub(r"`([^`]+)`", r"\\texttt{\1}", text)

        # Bold
        text = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", text)

        # Italic
        text = re.sub(r"\*([^*]+)\*", r"\\textit{\1}", text)

        # Links
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\\href{\2}{\1}", text)

        # Images (placeholder)
        text = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            r"\\includegraphics[width=0.8\\textwidth]{\2} % \1",
            text,
        )

        # 改进的表格处理
        lines = text.split('\n')
        in_table = False
        table_rows = []
        result_lines = []
        
        for line in lines:
            if '|' in line and not in_table:
                in_table = True
                table_rows = [line]
            elif '|' in line and in_table:
                table_rows.append(line)
            elif in_table:
                # 表格结束，进行转换
                if len(table_rows) >= 2:
                    latex_table = self._convert_markdown_table(table_rows)
                    result_lines.append(latex_table)
                in_table = False
                table_rows = []
                result_lines.append(line)
            else:
                result_lines.append(line)
        
        text = '\n'.join(result_lines)

        # Headers (shouldn't appear in body, but just in case)
        text = re.sub(r"^### (.+)$", r"\\subsubsection{\1}", text, flags=re.MULTILINE)
        text = re.sub(r"^## (.+)$", r"\\subsection{\1}", text, flags=re.MULTILINE)
        text = re.sub(r"^# (.+)$", r"\\section{\1}", text, flags=re.MULTILINE)

        # Unordered lists
        text = re.sub(r"^- (.+)$", r"\\item \1", text, flags=re.MULTILINE)
        text = re.sub(r"(\\item .+\n(?!\\item))", r"\1\n", text)

        # Math: $...$ → stays as is (LaTeX native)
        # Math: $$...$$ → \[...\]
        text = re.sub(r"\$\$(.+?)\$\$", r"\\\[\1\\\]", text, flags=re.DOTALL)

        return text

    def _convert_markdown_table(self, table_rows: List[str]) -> str:
        """将Markdown表格转换为LaTeX表格"""
        if not table_rows:
            return ""
        
        # 解析表格行
        parsed_rows = []
        for row in table_rows:
            cells = [c.strip() for c in row.split("|") if c.strip()]
            if cells:
                parsed_rows.append(cells)
        
        if len(parsed_rows) < 2:
            return ""
        
        # 确定列数
        num_columns = len(parsed_rows[0])
        
        # 生成列格式（默认居中）
        column_format = "|" + "c|" * num_columns
        
        # 构建表格内容
        table_content = []
        for i, row in enumerate(parsed_rows):
            if i == 1 and all(set(cell.strip()) <= {"-", ":", " "} for cell in row):
                continue  # 跳过分隔行
            
            # 处理单元格内容
            processed_cells = []
            for cell in row:
                # 移除Markdown格式
                cell = re.sub(r"\*\*(.*?)\*\*", r"\\textbf{\1}", cell)
                cell = re.sub(r"\*(.*?)\*", r"\\textit{\1}", cell)
                cell = re.sub(r"`(.*?)`", r"\\texttt{\1}", cell)
                processed_cells.append(cell)
            
            table_content.append(" & ".join(processed_cells) + " \\\ \hline")
        
        # 生成完整的LaTeX表格
        latex_table = """\begin{table}[htbp]
    \centering
    \begin{tabular}{TABLE_FORMAT}
        \hline
        TABLE_CONTENT
    \end{tabular}
    \caption{Table}
    \label{tab:table}
\end{table}
"""
        
        latex_table = latex_table.replace("TABLE_FORMAT", column_format)
        latex_table = latex_table.replace("TABLE_CONTENT", "\n        ".join(table_content))
        
        return latex_table

    def _table_row(self, row: str) -> str:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        if not cells:
            return ""
        if all(set(c.strip()) <= {"-", ":", " "} for c in cells):
            return ""  # separator row
        return " & ".join(cells) + " \\\ \hline\n"

    def _clean_latex(self, text: str) -> str:
        """清理常见的LaTeX问题"""
        # 修复连续空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 修复表格后的多余换行（使用原始字符串避免转义问题）
        text = re.sub(r"\\\\ \\hline\n+\\\\", r"\\\\ \\hline\n\\\\", text)
        return text

    def validate(self, context: "WorkflowContext") -> List[str]:
        errors = []
        if not context.get_state("polished_sections"):
            errors.append("No polished_sections found. Run WriteFlow steps first.")
        return errors


class LaTeXCompileStep(WorkflowStep):
    """LaTeX编译步骤

    使用pdflatex + bibtex编译LaTeX源码为PDF。
    自动检测latexmk或pdflatex是否可用。
    """

    def __init__(self, max_runs: int = 3):
        super().__init__(
            name="latex_compile",
            description="Compile LaTeX source to PDF"
        )
        self.max_runs = max_runs

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        # Check for LaTeX installation first (fail fast with clear message)
        latex_cmd = self._find_latex_command()
        if not latex_cmd:
            return {
                "success": False,
                "error": (
                    "LaTeX not installed. Install with:\n"
                    "  Ubuntu/Debian: sudo apt install texlive-latex-recommended texlive-fonts-recommended\n"
                    "  macOS: brew install --cask mactex-no-gui\n"
                    "  Or use latexmk for automated compilation."
                ),
            }

        latex_result = context.get_state("latex_render", {})
        tex_file = latex_result.get("tex_file")
        if not tex_file or not Path(tex_file).exists():
            return {"success": False, "error": "LaTeX source file not found"}

        work_dir = Path(tex_file).parent
        tex_name = Path(tex_file).stem

        logger.info(f"Compiling LaTeX with {latex_cmd} in {work_dir}")

        # Compile sequence: pdflatex → bibtex → pdflatex → pdflatex
        compile_log = []
        pdf_file = work_dir / f"{tex_name}.pdf"

        for run_num in range(self.max_runs):
            logger.info(f"LaTeX compile pass {run_num + 1}/{self.max_runs}")

            if latex_cmd == "latexmk":
                result = subprocess.run(
                    ["latexmk", "-pdf", "-interaction=nonstopmode", tex_name + ".tex"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            else:
                result = subprocess.run(
                    [latex_cmd, "-interaction=nonstopmode", tex_name + ".tex"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

            compile_log.append(result.stdout[-2000:] if result.stdout else "")  # last 2000 chars

            # Run bibtex after first pass if .bib exists
            if run_num == 0 and (work_dir / "references.bib").exists():
                bib_result = subprocess.run(
                    ["bibtex", tex_name],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if bib_result.returncode != 0:
                    logger.warning(f"BibTeX warnings: {bib_result.stderr[:500]}")

        success = pdf_file.exists()

        if success:
            logger.info(f"PDF generated: {pdf_file} ({pdf_file.stat().st_size} bytes)")
        else:
            # Extract error from log
            error_msg = self._extract_error(compile_log[-1]) if compile_log else "Unknown error"
            logger.error(f"LaTeX compilation failed: {error_msg}")

        return {
            "success": success,
            "pdf_file": str(pdf_file) if success else None,
            "tex_file": str(tex_file),
            "compile_log": compile_log,
            "error": self._extract_error(compile_log[-1]) if not success and compile_log else None,
        }

    def _find_latex_command(self) -> Optional[str]:
        """检测可用的LaTeX编译命令"""
        for cmd in ["latexmk", "pdflatex", "xelatex", "lualatex"]:
            if shutil.which(cmd):
                return cmd
        return None

    def _extract_error(self, log: str) -> str:
        """从LaTeX日志中提取错误信息"""
        if not log:
            return "Empty log"
        errors = re.findall(r"^! (.+)$", log, re.MULTILINE)
        return errors[0][:200] if errors else log[-200:]

    def validate(self, context: "WorkflowContext") -> List[str]:
        errors = []
        if not context.get_state("latex_render"):
            errors.append("No latex_render result found. Run LaTeX render step first.")
        return errors


class LaTeXFlow(Workflow):
    """LaTeXFlow - LaTeX论文生成与编译工作流

    完整工作流：
    1. 大纲生成（复用WriteFlow）
    2. 初稿撰写（复用WriteFlow）
    3. 语言润色（复用WriteFlow）
    4. LaTeX模板渲染
    5. LaTeX编译（pdflatex + bibtex）

    配置示例：
    ```yaml
    workflow:
      latex:
        authors: "Author One, Author Two"
        template: custom_template.tex  # 可选，自定义模板
        compile: true  # 是否自动编译PDF
    ```
    """

    def __init__(self,
                 model_gateway: ModelGateway,
                 config: Optional[Dict[str, Any]] = None,
                 workflow_id: str = "latex_flow",
                 storage_path: Optional[Path] = None):
        workflow_config = config or {}
        self._latex_config = workflow_config.get("latex", {})
        super().__init__(
            workflow_id=workflow_id,
            config=workflow_config,
            storage_path=storage_path or Path("./latex_output"),
            model_gateway=model_gateway,
        )

    def build_steps(self) -> List[WorkflowStep]:
        steps = [
            OutlineGenerationStep(self.model_gateway),
            DraftWritingStep(self.model_gateway),
            PolishingStep(self.model_gateway),
            LaTeXRenderStep(self.model_gateway),
        ]

        if self._latex_config.get("compile", True):
            steps.append(LaTeXCompileStep())

        return steps


__all__ = [
    "LaTeXFlow",
    "LaTeXRenderStep",
    "LaTeXCompileStep",
]
