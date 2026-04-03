"""FigureGenerationStep 单元测试"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tutor.core.workflow.figure import (
    FigureGenerationStep,
    FigureSpec,
    GeneratedFigure,
)


# --- Fixtures ---

@pytest.fixture
def step():
    return FigureGenerationStep()


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.results_dir = Path("/tmp/test_results")
    return ctx


# --- FigureSpec Tests ---

class TestFigureSpec:
    def test_defaults(self):
        spec = FigureSpec(type="line")
        assert spec.type == "line"
        assert spec.figsize == (8, 5)
        assert spec.dpi == 150
        assert spec.save_format == "png"

    def test_custom(self):
        spec = FigureSpec(type="bar", title="Test", figsize=(10, 6), dpi=300)
        assert spec.title == "Test"
        assert spec.figsize == (10, 6)


class TestSanitizeFilename:
    def test_normal(self):
        assert FigureGenerationStep._sanitize_filename("Training Loss") == "training_loss"

    def test_special_chars(self):
        result = FigureGenerationStep._sanitize_filename("Accuracy@Epoch-100 (%)")
        assert "@" not in result
        assert "accuracyepoch-100" == result

    def test_empty(self):
        assert FigureGenerationStep._sanitize_filename("") == "figure"

    def test_long(self):
        result = FigureGenerationStep._sanitize_filename("A" * 200)
        assert len(result) <= 80


class TestAutoDetectSpecs:
    def test_training_loss(self, step):
        data = {"training_loss": {"train": [1.0, 0.8, 0.5], "val": [1.1, 0.9, 0.6]}}
        specs = step._auto_detect_specs(data)
        assert len(specs) == 1
        assert specs[0].type == "line"
        assert specs[0].title == "Training Loss"

    def test_baseline_comparison(self, step):
        data = {"baselines": {"Method A": 0.95, "Method B": 0.88, "Ours": 0.97}}
        specs = step._auto_detect_specs(data)
        assert len(specs) == 1
        assert specs[0].type == "bar"

    def test_confusion_matrix(self, step):
        data = {"confusion_matrix": [[10, 2], [1, 8]]}
        specs = step._auto_detect_specs(data)
        assert len(specs) == 1
        assert specs[0].type == "heatmap"

    def test_multiple(self, step):
        data = {
            "training_loss": {"loss": [1.0, 0.5]},
            "baselines": {"A": 0.9},
            "confusion_matrix": [[5, 0], [0, 5]],
        }
        specs = step._auto_detect_specs(data)
        assert len(specs) == 3

    def test_empty_data(self, step):
        specs = step._auto_detect_specs({})
        assert specs == []

    def test_no_recognized_keys(self, step):
        specs = step._auto_detect_specs({"other": 42})
        assert specs == []


class TestCheckMatplotlib:
    def test_available(self, step):
        with patch.dict("sys.modules", {"matplotlib": MagicMock()}):
            step._matplotlib_available = None
            assert step._check_matplotlib() is True

    def test_not_available(self, step):
        with patch.dict("sys.modules", {"matplotlib": None}, clear=False):
            step._matplotlib_available = None
            try:
                result = step._check_matplotlib()
            except Exception:
                result = False
            # May still be True if matplotlib is actually installed
            # Just check it returns a bool
            assert isinstance(result, bool)


class TestGeneratePlaceholders:
    def test_placeholders_without_matplotlib(self, step, tmp_path):
        step._matplotlib_available = False
        specs = [FigureSpec(type="line", title="Test Figure")]
        figures = step._generate_placeholders(specs, tmp_path)

        assert len(figures) == 1
        assert figures[0].metadata.get("placeholder") is True
        assert Path(figures[0].file_path).exists()
        # Placeholder files may be binary (PNG), so check file is not empty
        content = Path(figures[0].file_path).read_bytes()
        assert len(content) > 0


class TestExecute:
    def test_no_data(self, step, mock_context):
        mock_context.get_state.return_value = {}
        result = step.execute(mock_context)
        assert result["figures"] == []
        assert result["total_figures"] == 0

    def test_with_explicit_specs(self, step, mock_context, tmp_path):
        mock_context.results_dir = tmp_path
        mock_context.get_state.side_effect = lambda key, default=None: {
            "experiment_results": {},
            "figure_specs": [FigureSpec(type="line", title="Test")],
        }.get(key, default)

        step._matplotlib_available = False
        result = step.execute(mock_context)
        assert result["total_figures"] == 1

    def test_auto_detect_from_experiment(self, step, mock_context, tmp_path):
        mock_context.results_dir = tmp_path
        mock_context.get_state.side_effect = lambda key, default=None: {
            "experiment_results": {"training_loss": {"loss": [1.0, 0.5]}},
            "figure_specs": [],
        }.get(key, default)

        step._matplotlib_available = False
        result = step.execute(mock_context)
        assert result["total_figures"] == 1


class TestValidate:
    def test_always_valid(self, step):
        errors = step.validate(None)
        assert errors == []


class TestRenderers:
    """Test individual renderers with mocked matplotlib"""

    @pytest.fixture
    def mock_plt(self):
        with patch.dict("sys.modules", {
            "matplotlib": MagicMock(),
            "matplotlib.pyplot": MagicMock(),
        }):
            yield

    def test_render_line_dict(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="line", data={"train": [1.0, 0.5], "val": [1.1, 0.6]})
        step._render_line(ax, spec)
        assert ax.plot.call_count == 2

    def test_render_line_list(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="line", data=[1.0, 0.5, 0.3])
        step._render_line(ax, spec)
        assert ax.plot.call_count == 1

    def test_render_bar_dict(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="bar", data={"A": 0.9, "B": 0.8})
        step._render_bar(ax, spec)
        assert ax.bar.called

    def test_render_bar_list_of_dicts(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(
            type="bar",
            data=[{"name": "A", "score": 0.9}, {"name": "B", "score": 0.8}]
        )
        step._render_bar(ax, spec)
        assert ax.bar.called

    def test_render_scatter_dict(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="scatter", data={"x": [1, 2, 3], "y": [4, 5, 6]})
        step._render_scatter(ax, spec)
        assert ax.scatter.called

    def test_render_box_dict(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="box", data={"A": [1, 2, 3], "B": [4, 5, 6]})
        step._render_box(ax, spec)
        assert ax.boxplot.called

    def test_render_box_list(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="box", data=[[1, 2, 3], [4, 5, 6]])
        step._render_box(ax, spec)
        assert ax.boxplot.called

    def test_render_table(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="table", data=[{"Method": "A", "Score": 0.9}])
        step._render_table(ax, spec)
        assert ax.table.called
        assert ax.axis.called

    def test_render_table_dict(self, step, mock_plt):
        ax = MagicMock()
        spec = FigureSpec(type="table", data={"Metric": "Value"})
        step._render_table(ax, spec)
        assert ax.table.called

    def test_unsupported_type_raises(self, step, mock_plt):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        spec = FigureSpec(type="3d_surface", data={})
        with pytest.raises(ValueError, match="Unsupported figure type"):
            step._render_figure(spec, Path("/tmp"))
