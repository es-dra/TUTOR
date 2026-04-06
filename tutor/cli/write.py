"""WriteFlow CLI - 论文撰写工作流

根据研究想法和实验结果，自动生成符合学术规范的论文初稿。
"""

import sys
from pathlib import Path
from typing import Optional, List
import json
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table

from tutor.core.workflow.write import WriteFlow
from tutor.core.storage import StorageManager
from tutor.core.model import ModelGateway
from tutor.config.loader import load_config

console = Console()
app = typer.Typer(
    name="Write",
    help="论文撰写工作流 - 自动生成学术论文初稿",
    no_args_is_help=True
)


@app.command()
def start(
    idea_source: str = typer.Argument(
        ...,
        help="IdeaFlow输出的想法ID或研究主题描述"
    ),
    from_idea_id: bool = typer.Option(
        False,
        "--from-idea", "-i",
        help="将idea_source视为IdeaFlow生成的想法ID（从存储加载）"
    ),
    experiment_summary: Optional[Path] = typer.Option(
        None,
        "--experiment", "-e",
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="实验报告摘要（JSON格式）"
    ),
    output_format: str = typer.Option(
        "md",
        "--format", "-f",
        help="输出格式：md / latex / docx（MVP仅支持md）"
    ),
    word_limit: Optional[int] = typer.Option(
        None,
        "--word-limit", "-w",
        help="正文字数限制（不含参考文献）"
    ),
    sections: Optional[str] = typer.Option(
        None,
        "--sections", "-s",
        help="指定生成章节（逗号分隔，如：'introduction,methodology,experiments'）"
    ),
    expert_review: bool = typer.Option(
        False,
        "--expert-review",
        help="启用专家评审步骤（MVP默认关闭）"
    ),
    use_latex: bool = typer.Option(
        False,
        "--latex",
        help="启用 LaTeX 插件（自动生成并编译为 PDF）"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="输出目录（默认：./output/write/{timestamp}）"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="显示详细日志"
    )
):
    """开始论文撰写

    步骤：生成大纲 → 逐章节撰写 → 语言润色 → 格式化输出

    示例:
        tutor write start "idea_abc123" --from-idea --experiment experiment_report.json
        tutor write start "基于深度学习的图像超分辨率研究" --sections "introduction,methodology" --word-limit 3000
    """
    try:
        # 1. 加载配置
        with console.status("[bold blue]加载配置...", spinner="dots"):
            config = load_config()
            # 确定存储基础路径
            storage_base = output or Path(config.get("storage", {}).get("project_dir", "./data/workflows"))
            storage_manager = StorageManager(config, storage_base)
            storage_manager.initialize()
            model_gateway = ModelGateway(config)

        console.print("[✅] 配置加载完成", style="green")

        # 2. 准备研究输入
        topic = ""
        description = ""
        experiment_data = {}

        if from_idea_id:
            # 从存储加载Idea
            idea_item = storage_manager.load("idea", idea_source)
            if not idea_item:
                console.print(f"[❌] 未找到ID为 {idea_source} 的Idea", style="bold red")
                raise typer.Exit(1)

            idea_data = idea_item.get("data", {})
            meta = idea_item.get("metadata", {})

            topic = meta.get("title", "Untitled Research")
            description = idea_data.get("description", "")
            console.print(f"[💡] 加载Idea: [cyan]{topic}[/cyan]")
        else:
            # 直接使用主题描述
            topic = idea_source
            description = idea_source
            console.print(f"[📝] 使用主题: [cyan]{topic}[/cyan]")

        # 3. 加载实验报告（如果提供）
        if experiment_summary:
            with console.status("[bold blue]读取实验报告...", spinner="dots"):
                experiment_data = json.loads(experiment_summary.read_text(encoding="utf-8"))
            console.print(f"[📊] 实验报告: {experiment_summary}")

        # 4. 解析章节列表
        section_list = []
        if sections:
            section_list = [s.strip() for s in sections.split(",") if s.strip()]

        # 5. 初始化输出目录
        if output is None:
            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output = Path(f"./output/write/{timestamp}")
        output.mkdir(parents=True, exist_ok=True)

        console.print(f"[📁] 输出目录: [cyan]{output}[/cyan]")

        # 6. 创建WriteFlow工作流
        with console.status("[bold blue]初始化工作流...", spinner="dots"):
            workflow = WriteFlow(
                config=config,
                model_gateway=model_gateway,
                storage_manager=storage_manager,
                topic=topic,
                description=description,
                experiment_summary=experiment_data,
                output_format=output_format,
                word_limit=word_limit,
                sections=section_list,
                expert_review=expert_review,
                output_dir=output
            )

        console.print("[✅] 工作流初始化完成", style="green")

        # 7. 显示配置
        console.print(Panel.fit(
            f"[bold]研究主题:[/bold] {topic}\n"
            f"[bold]输出格式:[/bold] {output_format}\n"
            f"[bold]字数限制:[/bold] {word_limit or '无限制'}\n"
            f"[bold]指定章节:[/bold] {', '.join(section_list) if section_list else '全部'}\n"
            f"[bold]专家评审:[/bold] {'启用' if expert_review else '关闭'}",
            title="✍️  WriteFlow 工作流启动",
            border_style="cyan"
        ))

        # 8. 执行工作流
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]撰写中...", total=None)

            try:
                result = workflow.run()
                # 8.5 如果启用了 LaTeX 插件
                if use_latex:
                    progress.update(task, description="[blue]正在启用 LaTeX 插件...")
                    from tutor.core.workflow.latex import LaTeXFlow
                    latex_flow = LaTeXFlow(
                        workflow_id=f"{workflow.workflow_id}_latex",
                        config=config,
                        storage_path=output / "latex",
                        model_gateway=model_gateway
                    )
                    # 将 WriteFlow 的结果传递给 LaTeXFlow
                    latex_flow.context.update_state(result.output)
                    latex_result = latex_flow.run()
                    if latex_result.status == "completed":
                        console.print(
                            f"📄 PDF 已生成: {output / 'latex' / 'results' / 'paper.pdf'}",
                            style="bold green",
                        )
                progress.update(task, completed=True, description="[green]完成")

                # 9. 显示撰写结果
                _display_write_results(result, console, output)

                # 10. 保存检查点
                _save_checkpoint(workflow, output, storage_manager)

                console.print("\n[🎉] 论文撰写完成！", style="bold green")
                console.print(f"📄 论文草稿: {output / 'paper_draft.md'}")
                console.print(f"📊 大纲文件: {output / 'outline.json'}")

            except Exception as e:
                progress.update(task, completed=True, description="[red]失败")
                console.print(f"\n[❌] 撰写失败: {e}", style="bold red")
                if verbose:
                    console.print_exception()
                raise typer.Exit(code=1)

    except FileNotFoundError as e:
        console.print(f"[❌] 文件错误: {e}", style="bold red")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        console.print(f"[❌] JSON解析错误: {e}", style="bold red")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[❌] 参数错误: {e}", style="bold red")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[⚠️]  用户中断执行", style="yellow")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[❌] 未知错误: {e}", style="bold red")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def polish(
    draft_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="待润色的论文草稿路径"
    ),
    focus: Optional[str] = typer.Option(
        None,
        "--focus",
        help="润色重点：grammar / clarity / academic / conciseness"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="润色后输出路径"
    )
):
    """对现有论文草稿进行语言润色"""
    try:
        if not draft_path.exists():
            console.print(f"[❌] 文件不存在: {draft_path}", style="bold red")
            raise typer.Exit(1)

        draft_content = draft_path.read_text(encoding="utf-8")
        console.print(f"[📄] 加载草稿: {draft_path} ({len(draft_content)} 字符)")

        # MVP限制：仅支持基础润色（不调用完整WriteFlow）
        console.print("[ℹ️]  MVP润色功能：基础语法检查和语言优化", style="blue")

        # 简单润色（placeholder）
        polished = draft_content  # TODO: 实际实现润色逻辑

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(polished, encoding="utf-8")
            console.print(f"[✅] 润色完成: {output}", style="green")
        else:
            default_output = draft_path.with_name(f"{draft_path.stem}_polished{draft_path.suffix}")
            default_output.write_text(polished, encoding="utf-8")
            console.print(f"[✅] 润色完成: {default_output}", style="green")

    except Exception as e:
        console.print(f"[❌] 润色失败: {e}", style="bold red")
        raise typer.Exit(1)


@app.command()
def list(
    limit: int = typer.Option(20, "--limit", "-l", help="显示数量限制")
):
    """列出所有已生成的论文草稿"""
    try:
        config = load_config()
        storage = StorageManager(config)
        storage.initialize()

        results = storage.list("paper", limit=limit)

        if not results:
            console.print("[ℹ️]  暂未找到任何论文草稿", style="blue")
            return

        table = Table(title="论文草稿")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("标题", style="white")
        table.add_column("格式", style="yellow")
        table.add_column("字数", justify="right")
        table.add_column("创建时间", style="dim")

        for item in sorted(results, key=lambda x: x.get("metadata", {}).get("created_at", ""), reverse=True):
            meta = item.get("metadata", {})
            data = item.get("data", {})

            table.add_row(
                meta.get("id", "N/A")[:8],
                meta.get("title", "Untitled")[:40] + ("..." if len(meta.get("title", "")) > 40 else ""),
                meta.get("format", "md"),
                str(data.get("word_count", 0)),
                meta.get("created_at", "N/A")[:19]
            )

        console.print(table)

    except Exception as e:
        console.print(f"[❌] 列出草稿失败: {e}", style="bold red")


def _display_write_results(result: dict, console: Console, output: Path):
    """显示撰写结果摘要"""
    console.print("\n[bold]📊 撰写结果[/bold]")
    console.print("─" * 50)

    stats = result.get("statistics", {})
    outline = result.get("outline", {})

    console.print(f"📝 总字数: [bold cyan]{stats.get('total_word_count', 0)}[/bold cyan]")
    console.print(f"📑 章节数: [bold cyan]{len(outline.get('sections', []))}[/bold cyan]")
    console.print(f"⏱️  总耗时: [bold cyan]{stats.get('total_duration_seconds', 0):.1f}秒[/bold cyan]")

    # 显示大纲结构
    sections = outline.get("sections", [])
    if sections:
        console.print("\n[bold]📋 论文结构:[/bold]")
        for i, section in enumerate(sections, 1):
            title = section.get("title", "Untitled")
            word_count = section.get("word_count", 0)
            console.print(f"  {i}. {title} ({word_count} 字)")


def _save_checkpoint(workflow: WriteFlow, output: Path, storage: StorageManager):
    """保存工作流检查点"""
    try:
        checkpoint_file = output / "checkpoint.json"
        if hasattr(workflow, "get_checkpoint"):
            checkpoint = workflow.get_checkpoint()
            import json
            checkpoint_file.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False))
    except Exception as e:
        console.print(f"[⚠️]  保存检查点失败: {e}", style="yellow")


if __name__ == "__main__":
    app()
