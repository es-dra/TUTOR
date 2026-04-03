"""LaTeXFlow 单元测试"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tutor.core.workflow.latex import (
    LaTeXRenderStep,
    LaTeXCompileStep,
    LaTeXFlow,
    DEFAULT_LATEX_TEMPLATE,
)


# --- Fixtures ---

@pytest.fixture
def mock_model_gateway():
    mg = MagicMock()
    mg.generate.return_value = "Generated content"
    return mg


@pytest.fixture
def mock_context(tmp_path):
    ctx = MagicMock()
    ctx.results_dir = tmp_path / "test_results"
    ctx.config = {"latex": {"authors": "Test Author"}}
    return ctx


@pytest.fixture
def sample_outline():
    return {
        "sections": [
            {"title": "Title", "content": "My Research Paper"},
            {"title": "Abstract", "content": "This is the abstract."},
            {"title": "Introduction", "content": "Introduction text."},
        ]
    }


@pytest.fixture
def sample_sections():
    return {
        "Abstract": {"content": "This is the abstract.", "level": 2, "word_count": 20},
        "Introduction": {"content": "## Background\nSome background.\n\n## Problem\nA problem.", "level": 2, "word_count": 50},
        "Methodology": {"content": "We propose a method.", "level": 2, "word_count": 30},
    }


# --- LaTeXRenderStep Tests ---

class TestLaTeXRenderStep:
    def test_execute_produces_latex(self, mock_model_gateway, mock_context, sample_outline, sample_sections):
        step = LaTeXRenderStep(mock_model_gateway)
        mock_context.get_state.side_effect = lambda key, default=None: {
            "outline": sample_outline,
            "polished_sections": sample_sections,
        }.get(key, default)

        result = step.execute(mock_context)

        assert "latex_source" in result
        assert "tex_file" in result
        assert "bib_file" in result
        assert "\\documentclass" in result["latex_source"]
        assert "\\begin{document}" in result["latex_source"]
        assert "\\end{document}" in result["latex_source"]
        assert result["section_count"] >= 1

    def test_title_extraction(self, mock_model_gateway):
        step = LaTeXRenderStep(mock_model_gateway)
        outline = {"sections": [{"title": "Title", "content": "My Paper"}]}
        assert step._extract_title(outline) == "My Paper"

    def test_title_fallback(self, mock_model_gateway):
        step = LaTeXRenderStep(mock_model_gateway)
        assert step._extract_title({}) == "Untitled Paper"


class TestMarkdownToLatex:
    def setup_method(self):
        self.step = LaTeXRenderStep(MagicMock())

    def test_bold(self):
        assert self.step._markdown_to_latex("**bold**") == "\\textbf{bold}"

    def test_italic(self):
        assert self.step._markdown_to_latex("*italic*") == "\\textit{italic}"

    def test_inline_code(self):
        assert self.step._markdown_to_latex("`code`") == "\\texttt{code}"

    def test_link(self):
        result = self.step._markdown_to_latex("[text](http://example.com)")
        assert "\\href{http://example.com}{text}" in result

    def test_code_block(self):
        md = "```python\nprint('hi')\n```"
        result = self.step._markdown_to_latex(md)
        assert "\\begin{verbatim}" in result
        assert "\\end{verbatim}" in result

    def test_display_math(self):
        result = self.step._markdown_to_latex("$$x^2$$")
        assert "\\[" in result and "\\]" in result

    def test_list_items(self):
        result = self.step._markdown_to_latex("- item 1\n- item 2")
        assert "\\item item 1" in result
        assert "\\item item 2" in result

    def test_headers(self):
        result = self.step._markdown_to_latex("## Section\n### Subsection")
        assert "\\subsection{Section}" in result
        assert "\\subsubsection{Subsection}" in result


class TestCleanLatex:
    def setup_method(self):
        self.step = LaTeXRenderStep(MagicMock())

    def test_collapse_multiple_blank_lines(self):
        text = "line1\n\n\n\nline2"
        assert self.step._clean_latex(text) == "line1\n\nline2"

    def test_no_change_needed(self):
        text = "line1\n\nline2"
        assert self.step._clean_latex(text) == "line1\n\nline2"


# --- LaTeXCompileStep Tests ---

class TestLaTeXCompileStep:
    def test_find_latex_none(self):
        with patch("shutil.which", return_value=None):
            step = LaTeXCompileStep()
            assert step._find_latex_command() is None

    def test_find_latex_pdflatex(self):
        with patch("shutil.which", side_effect=lambda cmd: cmd == "pdflatex"):
            step = LaTeXCompileStep()
            assert step._find_latex_command() == "pdflatex"

    def test_find_latex_latexmk_priority(self):
        with patch("shutil.which", return_value=True):
            step = LaTeXCompileStep()
            assert step._find_latex_command() == "latexmk"

    def test_extract_error_bang(self):
        log = "! Undefined control sequence.\nl.10 \\badcmd\n?"
        step = LaTeXCompileStep()
        assert "Undefined control sequence" in step._extract_error(log)

    def test_extract_error_empty(self):
        step = LaTeXCompileStep()
        assert step._extract_error("") == "Empty log"

    def test_execute_no_latex_installed(self, mock_context):
        step = LaTeXCompileStep()
        mock_context.get_state.return_value = {
            "tex_file": "/tmp/test.tex",
            "latex_source": "",
        }

        with patch.object(step, "_find_latex_command", return_value=None):
            result = step.execute(mock_context)

        assert result["success"] is False
        assert "not installed" in result["error"]

    def test_validate_missing_render(self, mock_context):
        step = LaTeXCompileStep()
        mock_context.get_state.return_value = None
        errors = step.validate(mock_context)
        assert len(errors) >= 1


# --- LaTeXFlow Tests ---

class TestLaTeXFlow:
    def test_build_steps_default_compile(self, mock_model_gateway):
        flow = LaTeXFlow(mock_model_gateway, config={"latex": {"compile": True}})
        steps = flow.build_steps()
        step_names = [s.name for s in steps]
        assert "latex_render" in step_names
        assert "latex_compile" in step_names

    def test_build_steps_no_compile(self, mock_model_gateway):
        flow = LaTeXFlow(mock_model_gateway, config={"latex": {"compile": False}})
        steps = flow.build_steps()
        step_names = [s.name for s in steps]
        assert "latex_render" in step_names
        assert "latex_compile" not in step_names

    def test_build_steps_default_config(self, mock_model_gateway):
        flow = LaTeXFlow(mock_model_gateway)
        steps = flow.build_steps()
        step_names = [s.name for s in steps]
        # Default should compile
        assert "latex_compile" in step_names


class TestDefaultTemplate:
    def test_template_has_placeholders(self):
        assert "TUTOR_TITLE" in DEFAULT_LATEX_TEMPLATE
        assert "TUTOR_AUTHORS" in DEFAULT_LATEX_TEMPLATE
        assert "TUTOR_ABSTRACT" in DEFAULT_LATEX_TEMPLATE
        assert "TUTOR_BODY" in DEFAULT_LATEX_TEMPLATE

    def test_template_has_document_env(self):
        assert "\\begin{document}" in DEFAULT_LATEX_TEMPLATE
        assert "\\end{document}" in DEFAULT_LATEX_TEMPLATE

    def test_template_has_common_packages(self):
        assert "amsmath" in DEFAULT_LATEX_TEMPLATE
        assert "hyperref" in DEFAULT_LATEX_TEMPLATE
        assert "graphicx" in DEFAULT_LATEX_TEMPLATE
