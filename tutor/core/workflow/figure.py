"""FigureGenerationStep - 自动图表生成

根据实验结果数据自动生成matplotlib图表，支持多种常见科研图表类型。

支持的图表类型：
- line: 折线图（训练曲线、性能趋势）
- bar: 柱状图（基线对比、消融实验）
- heatmap: 热力图（混淆矩阵、注意力权重）
- scatter: 散点图（相关性分析）
- box: 箱线图（分布比较）
- table: 表格渲染为图片（结果汇总表）

使用方式：
    from core.workflow.figure import FigureGenerationStep, FigureSpec

    step = FigureGenerationStep()
    specs = [
        FigureSpec(type="line", title="Training Loss", data=loss_data,
                   x_label="Epoch", y_label="Loss"),
        FigureSpec(type="bar", title="Baseline Comparison", data=baseline_data,
                   x_label="Method", y_label="Accuracy"),
    ]
    result = step.generate(specs, output_dir=Path("./figures"))
"""

import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from tutor.core.workflow.base import WorkflowStep

logger = logging.getLogger(__name__)


@dataclass
class FigureSpec:
    """图表生成规格"""
    type: str  # line, bar, heatmap, scatter, box, table
    title: str = ""
    data: Any = None
    x_label: str = ""
    y_label: str = ""
    figsize: Tuple[float, float] = (8, 5)
    dpi: int = 150
    style: str = "seaborn-v0_8-whitegrid"
    legend: bool = True
    save_format: str = "png"  # png, pdf, svg
    color_map: str = "viridis"
    # Additional matplotlib kwargs
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedFigure:
    """生成的图表结果"""
    spec: FigureSpec
    file_path: str
    file_size: int
    base64_data: str = ""  # Base64编码，便于嵌入LaTeX/HTML
    metadata: Dict[str, Any] = field(default_factory=dict)


class FigureGenerationStep(WorkflowStep):
    """自动图表生成步骤

    从实验结果中提取数据并自动生成科研级图表。
    支持多种图表类型和自定义样式。
    """

    SUPPORTED_TYPES = {"line", "bar", "heatmap", "scatter", "box", "table"}

    def __init__(self):
        super().__init__(
            name="figure_generation",
            description="Generate publication-quality figures from experiment data"
        )
        self._matplotlib_available: Optional[bool] = None

    def _check_matplotlib(self) -> bool:
        """延迟检查matplotlib是否可用"""
        if self._matplotlib_available is None:
            try:
                import matplotlib
                matplotlib.use("Agg")  # Non-interactive backend
                self._matplotlib_available = True
            except ImportError:
                self._matplotlib_available = False
                logger.warning("matplotlib not installed. Figure generation will return placeholder data.")
        return self._matplotlib_available

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        """从上下文提取数据并生成图表"""
        experiment_data = context.get_state("experiment_results", {})
        figure_specs = context.get_state("figure_specs", [])

        # If no explicit specs, auto-detect from experiment data
        if not figure_specs and experiment_data:
            figure_specs = self._auto_detect_specs(experiment_data)

        if not figure_specs:
            return {
                "figures": [],
                "figure_files": [],
                "total_figures": 0,
                "message": "No figure specs or experiment data found",
            }

        output_dir = context.results_dir / "figures"
        output_dir.mkdir(parents=True, exist_ok=True)

        figures = self.generate(figure_specs, output_dir)

        return {
            "figures": [f.metadata for f in figures],
            "figure_files": [f.file_path for f in figures],
            "total_figures": len(figures),
            "output_dir": str(output_dir),
        }

    def _auto_detect_specs(self, data: Dict) -> List[FigureSpec]:
        """从实验数据自动推断图表类型"""
        specs = []

        # Check for training curves
        if "training_loss" in data or "loss_curve" in data:
            loss_data = data.get("training_loss", data.get("loss_curve", {}))
            specs.append(FigureSpec(
                type="line",
                title="Training Loss",
                data=loss_data,
                x_label="Epoch",
                y_label="Loss",
            ))

        # Check for baseline comparison
        if "baselines" in data or "comparison" in data:
            comp_data = data.get("baselines", data.get("comparison", {}))
            specs.append(FigureSpec(
                type="bar",
                title="Baseline Comparison",
                data=comp_data,
                x_label="Method",
                y_label="Performance",
            ))

        # Check for confusion matrix
        if "confusion_matrix" in data:
            specs.append(FigureSpec(
                type="heatmap",
                title="Confusion Matrix",
                data=data["confusion_matrix"],
                x_label="Predicted",
                y_label="True",
            ))

        return specs

    def generate(
        self,
        specs: List[FigureSpec],
        output_dir: Path,
    ) -> List[GeneratedFigure]:
        """批量生成图表

        Args:
            specs: 图表规格列表
            output_dir: 输出目录

        Returns:
            GeneratedFigure列表
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self._check_matplotlib():
            return self._generate_placeholders(specs, output_dir)

        figures = []
        for spec in specs:
            try:
                figure = self._render_figure(spec, output_dir)
                figures.append(figure)
                logger.info(f"Generated figure: {figure.file_path}")
            except Exception as e:
                logger.error(f"Failed to generate figure '{spec.title}': {e}")
                figures.append(GeneratedFigure(
                    spec=spec,
                    file_path="",
                    file_size=0,
                    metadata={"error": str(e), "title": spec.title},
                ))

        return figures

    def _render_figure(self, spec: FigureSpec, output_dir: Path) -> GeneratedFigure:
        """渲染单个图表"""
        renderer = {
            "line": self._render_line,
            "bar": self._render_bar,
            "heatmap": self._render_heatmap,
            "scatter": self._render_scatter,
            "box": self._render_box,
            "table": self._render_table,
        }.get(spec.type)

        if not renderer:
            raise ValueError(f"Unsupported figure type: {spec.type}")

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.style.use(spec.style if spec.style else "seaborn-v0_8-whitegrid")
        fig, ax = plt.subplots(figsize=spec.figsize)

        renderer(ax, spec)

        ax.set_title(spec.title, fontsize=14, fontweight="bold")
        ax.set_xlabel(spec.x_label, fontsize=11)
        ax.set_ylabel(spec.y_label, fontsize=11)
        if spec.legend:
            ax.legend(fontsize=9)

        fig.tight_layout()

        # Save
        filename = self._sanitize_filename(spec.title or spec.type)
        filepath = output_dir / f"{filename}.{spec.save_format}"

        fig.savefig(str(filepath), dpi=spec.dpi, bbox_inches="tight")
        file_size = filepath.stat().st_size

        # Base64 for embedding
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=spec.dpi, bbox_inches="tight")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        plt.close(fig)

        return GeneratedFigure(
            spec=spec,
            file_path=str(filepath),
            file_size=file_size,
            base64_data=b64,
            metadata={
                "title": spec.title,
                "type": spec.type,
                "file_path": str(filepath),
                "file_size": file_size,
                "format": spec.save_format,
                "dpi": spec.dpi,
                "figsize": list(spec.figsize),
            },
        )

    # --- Renderers ---

    def _render_line(self, ax, spec: FigureSpec):
        """折线图"""
        data = spec.data
        if isinstance(data, dict):
            for label, values in data.items():
                if isinstance(values, (list, tuple)):
                    ax.plot(values, label=label, **spec.kwargs)
                elif isinstance(values, dict):
                    x = values.get("x", list(range(len(values.get("y", [])))))
                    y = values.get("y", [])
                    ax.plot(x, y, label=label, **spec.kwargs)
        elif isinstance(data, list):
            ax.plot(data, label=spec.y_label, **spec.kwargs)

    def _render_bar(self, ax, spec: FigureSpec):
        """柱状图"""
        data = spec.data
        if isinstance(data, dict):
            labels = list(data.keys())
            values = list(data.values())
            colors = spec.kwargs.pop("color", None)
            ax.bar(labels, values, color=colors, **spec.kwargs)
            if spec.kwargs.get("horizontal"):
                ax.barh(labels, values, **spec.kwargs)
        elif isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict):
                labels = [d.get("name", d.get("label", str(i))) for i, d in enumerate(data)]
                values = [d.get("value", d.get("score", 0)) for d in data]
                ax.bar(labels, values, **spec.kwargs)
            else:
                ax.bar(range(len(data)), data, **spec.kwargs)

    def _render_heatmap(self, ax, spec: FigureSpec):
        """热力图"""
        import matplotlib.pyplot as plt
        data = spec.data
        im = ax.imshow(data, cmap=spec.color_map, **spec.kwargs)
        plt.colorbar(im, ax=ax)

    def _render_scatter(self, ax, spec: FigureSpec):
        """散点图"""
        data = spec.data
        if isinstance(data, dict):
            x = data.get("x", [])
            y = data.get("y", [])
            c = data.get("c", None)
            s = data.get("s", None)
            ax.scatter(x, y, c=c, s=s, **spec.kwargs)
        elif isinstance(data, list) and len(data) >= 2:
            ax.scatter(data[0], data[1], **spec.kwargs)

    def _render_box(self, ax, spec: FigureSpec):
        """箱线图"""
        data = spec.data
        if isinstance(data, dict):
            ax.boxplot(list(data.values()), labels=list(data.keys()), **spec.kwargs)
        elif isinstance(data, list):
            ax.boxplot(data, **spec.kwargs)

    def _render_table(self, ax, spec: FigureSpec):
        """表格渲染为图片"""
        data = spec.data
        if isinstance(data, list) and len(data) > 0:
            # First row as header
            table_data = data
            ax.axis("off")
            ax.table(
                cellText=[list(row.values()) if isinstance(row, dict) else row
                          for row in table_data[1:]],
                colLabels=(list(table_data[0].keys()) if isinstance(table_data[0], dict)
                           else table_data[0]),
                loc="center",
                cellLoc="center",
            )
        elif isinstance(data, dict):
            ax.axis("off")
            ax.table(
                cellText=[[v] for v in data.values()],
                rowLabels=list(data.keys()),
                loc="center",
                cellLoc="center",
            )

    # --- Utilities ---

    # Minimal 100x20 gray PNG placeholder (base64-decoded)
    _PLACEHOLDER_PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAGQAAAAbCAYAAAB/f6w7AAAAiklEQVR42u3OMQ0AAAgEoNO/"
        "NBLowdHMe4HBJHYBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKx8fhMAAAAA"
    )

    def _generate_placeholders(
        self, specs: List[FigureSpec], output_dir: Path
    ) -> List[GeneratedFigure]:
        """matplotlib不可用时生成占位图像

        生成一个最小有效的PNG占位符，而非.txt文件，
        以确保LaTeX文档可以正常编译。
        """
        import struct
        figures = []
        for spec in specs:
            filename = self._sanitize_filename(spec.title or spec.type)
            filepath = output_dir / f"{filename}.png"

            # 生成带标题文本的PNG占位符
            png_data = self._create_text_png_placeholder(
                width=400,
                height=60,
                text=f"[Placeholder] {spec.title}\nType: {spec.type}\nInstall matplotlib for actual figures"
            )

            filepath.write_bytes(png_data)
            file_size = filepath.stat().st_size

            # Base64 for embedding
            b64 = base64.b64encode(png_data).decode("utf-8")

            figures.append(GeneratedFigure(
                spec=spec,
                file_path=str(filepath),
                file_size=file_size,
                base64_data=b64,
                metadata={
                    "title": spec.title,
                    "type": spec.type,
                    "placeholder": True,
                    "note": "matplotlib not installed - placeholder image"
                },
            ))
        return figures

    def _create_text_png_placeholder(
        self, width: int, height: int, text: str
    ) -> bytes:
        """创建包含文本的PNG占位符（不依赖matplotlib）

        使用纯Python生成一个简单的位图PNG。
        """
        # 使用PIL/Pillow如果可用，否则回退到最小PNG
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new("RGB", (width, height), color="#f0f0f0")
            draw = ImageDraw.Draw(img)
            # 尝试使用默认字体
            try:
                draw.text((10, 10), text, fill="#333333")
            except Exception:
                # 如果默认字体失败，使用更简单的方法
                draw.text((10, 10), text, fill="#333333")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            # PIL也不可用时，使用预先生成的最小PNG
            import zlib
            # 创建一个简单的100x30灰色PNG
            width, height = 100, 30
            raw_data = b""

            # PNG header
            signature = b"\x89PNG\r\n\x1a\n"

            # IHDR chunk (image header)
            ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xffffffff
            ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

            # IDAT chunk (image data)
            raw = b""
            for y in range(height):
                raw += b"\x00"  # filter type
                for x in range(width):
                    # Gray color #cccccc
                    raw += b"\xcc\xcc\xcc"
            compressed = zlib.compress(raw)
            idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xffffffff
            idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

            # IEND chunk
            iend_crc = zlib.crc32(b"IEND") & 0xffffffff
            iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

            return signature + ihdr + idat + iend

    @staticmethod
    def _sanitize_filename(title: str) -> str:
        """将标题转为安全文件名"""
        import re
        name = re.sub(r"[^a-zA-Z0-9_\- ]", "", title).strip().lower()
        name = re.sub(r"\s+", "_", name)
        return name[:80] or "figure"

    def validate(self, context: "WorkflowContext") -> List[str]:
        return []


__all__ = [
    "FigureGenerationStep",
    "FigureSpec",
    "GeneratedFigure",
]
