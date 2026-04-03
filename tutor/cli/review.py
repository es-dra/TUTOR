"""ReviewFlow CLI - 论文审核工作流

对完成的论文进行多维度审核，评估创新性、方法严谨性、实验完整性和写作质量。
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

from tutor.core.workflow.review import ReviewFlow
from tutor.core.storage import StorageManager
from tutor.core.model import ModelGateway
from tutor.config.loader import load_config

console = Console()
app = typer.Typer(
    name="Review",
    help="论文审核工作流 - 多维度评审与反馈",
    no_args_is_help=True
)


@app.command()
def review(
    draft_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="论文草稿文件路径（Markdown或LaTeX）"
    ),
    experiment_report: Optional[Path] = typer.Option(
        None,
        "--experiment", "-e",
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="相关实验报告（JSON格式）"
    ),
    reviewer_roles: Optional[List[str]] = typer.Option(
        None,
        "--roles", "-r",
        help="评审角色列表（MVP仅支持单角色：expert/innovator/skeptic/pragmatist）"
    ),
    feedback_detail: str = typer.Option(
        "detailed",
        "--detail", "-d",
        help="反馈详细度：brief 或 detailed"
    ),
    focus_areas: Optional[str] = typer.Option(
        None,
        "--focus", "-f",
        help="重点关注领域（逗号分隔，如：'methodology,experiments'）"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="评审报告输出路径"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="显示详细日志"
    )
):
    """执行论文审核

    步骤：加载草稿 → 整合实验报告 → 多维度评审 → 生成反馈报告

    示例:
        tutor review review paper.md --experiment experiment_report.json
        tutor review review draft.md --roles expert --focus "innovation, methodology"
    """
    try:
        # 1. 加载配置
        with console.status("[bold blue]加载配置...", spinner="dots"):
            config = load_config()
            # 确定存储基础路径
            storage_base = Path(config.get("storage", {}).get("project_dir", "./data/workflows"))
            storage_manager = StorageManager(config, storage_base)
            storage_manager.initialize()
            model_gateway = ModelGateway(config)

        console.print("[✅] 配置加载完成", style="green")

        # 2. 读取论文草稿
        with console.status("[bold blue]读取论文草稿...", spinner="dots"):
            draft_content = draft_path.read_text(encoding="utf-8")
        console.print(f"[📄] 草稿文件: {draft_path} ({len(draft_content)} 字符)")

        # 3. 读取实验报告（如果提供）
        experiment_data = {}
        if experiment_report:
            with console.status("[bold blue]读取实验报告...", spinner="dots"):
                experiment_data = json.loads(experiment_report.read_text(encoding="utf-8"))
            console.print(f"[📊] 实验报告: {experiment_report}")

        # 4. 解析关注领域
        focus_list = []
        if focus_areas:
            focus_list = [area.strip() for area in focus_areas.split(",") if area.strip()]

        # 5. MVP限制：单角色评审
        if reviewer_roles and len(reviewer_roles) > 1:
            console.print("[⚠️]  MVP当前仅支持单角色评审，将使用第一个角色", style="yellow")
        review_role = (reviewer_roles or ["expert"])[0]

        # 6. 创建ReviewFlow工作流
        with console.status("[bold blue]初始化工作流...", spinner="dots"):
            workflow = ReviewFlow(
                config=config,
                model_gateway=model_gateway,
                storage_manager=storage_manager,
                draft_content=draft_content,
                experiment_data=experiment_data,
                reviewer_role=review_role,
                feedback_detail=feedback_detail,
                focus_areas=focus_list
            )

        console.print("[✅] 工作流初始化完成", style="green")

        # 7. 显示配置
        console.print(Panel.fit(
            f"[bold]草稿文件:[/bold] {draft_path.name}\n"
            f"[bold]评审角色:[/bold] {review_role}\n"
            f"[bold]反馈详细度:[/bold] {feedback_detail}\n"
            f"[bold]关注领域:[/bold] {', '.join(focus_list) if focus_list else '全部'}",
            title="📝 ReviewFlow 工作流启动",
            border_style="magenta"
        ))

        # 8. 执行工作流
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]评审中...", total=None)

            try:
                result = workflow.run()
                progress.update(task, completed=True, description="[green]完成")

                # 9. 显示评审结果
                _display_review_results(result, console, output)

                # 10. 保存检查点
                _save_checkpoint(workflow, storage_manager)

                console.print("\n[🎉] 论文评审完成！", style="bold green")
                if output:
                    console.print(f"📄 评审报告: {output}")
                else:
                    console.print("📄 评审报告已生成到默认输出目录")

            except Exception as e:
                progress.update(task, completed=True, description="[red]失败")
                console.print(f"\n[❌] 评审失败: {e}", style="bold red")
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


def _display_review_results(result: dict, console: Console, output_path: Optional[Path]):
    """显示评审结果摘要"""
    console.print("\n[bold]📊 评审结果[/bold]")
    console.print("─" * 50)

    scores = result.get("scores", {})
    overall = result.get("overall_score", 0)

    console.print(f"🏅 总体评分: [bold green]{overall:.2f}/1.0[/bold green]")

    if scores:
        console.print("\n[bold]各维度评分:[/bold]")
        for dimension, score in scores.items():
            console.print(f"  {dimension}: [cyan]{score:.2f}[/cyan]")

    # 显示反馈摘要
    feedback = result.get("review_feedback", {})
    if feedback:
        console.print("\n[bold]💬 关键反馈:[/bold]")
        strengths = feedback.get("strengths", [])
        weaknesses = feedback.get("weaknesses", [])
        suggestions = feedback.get("suggestions", [])

        if strengths:
            console.print("\n[green]✓ 优点:[/green]")
            for s in strengths[:3]:
                console.print(f"  • {s}")

        if weaknesses:
            console.print("\n[red]✗ 不足:[/red]")
            for w in weaknesses[:3]:
                console.print(f"  • {w}")

        if suggestions:
            console.print("\n[yellow]➜ 改进建议:[/yellow]")
            for s in suggestions[:3]:
                console.print(f"  • {s}")

    # 生成报告文件
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_md = _generate_review_report(result)
        output_path.write_text(report_md, encoding="utf-8")
    else:
        # 默认输出到实验输出目录
        from datetime import datetime, timezone
        default_dir = Path(f"./output/review/{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
        default_dir.mkdir(parents=True, exist_ok=True)
        report_file = default_dir / "review_report.md"
        report_md = _generate_review_report(result)
        report_file.write_text(report_md, encoding="utf-8")
        output_path = report_file
        console.print(f"[📄] 详细报告已保存: {output_path}")


def _save_checkpoint(workflow: ReviewFlow, storage: StorageManager):
    """保存工作流检查点"""
    try:
        if hasattr(workflow, "get_checkpoint"):
            checkpoint = workflow.get_checkpoint()
            import json
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            checkpoint_file = Path(f"./output/review/checkpoint_{ts}.json")
            checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_file.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False))
    except Exception as e:
        console.print(f"[⚠️]  保存检查点失败: {e}", style="yellow")


def _generate_review_report(result: dict) -> str:
    """生成评审报告的Markdown格式"""
    scores = result.get("scores", {})
    overall = result.get("overall_score", 0)
    feedback = result.get("review_feedback", {})

    md = f"""# 论文评审报告

## 总体评分

**{overall:.2f} / 1.0**

## 维度评分

| 维度 | 分数 |
|------|------|
"""
    for dim, score in scores.items():
        md += f"| {dim} | {score:.2f} |\n"

    strengths = feedback.get("strengths", [])
    weaknesses = feedback.get("weaknesses", [])
    suggestions = feedback.get("suggestions", [])

    if strengths:
        md += "\n## 优点\n\n"
        for s in strengths:
            md += f"- {s}\n"

    if weaknesses:
        md += "\n## 不足\n\n"
        for w in weaknesses:
            md += f"- {w}\n"

    if suggestions:
        md += "\n## 改进建议\n\n"
        for s in suggestions:
            md += f"- {s}\n"

    # 详细评论（如果存在）
    detailed = feedback.get("detailed_comments", {})
    if detailed:
        md += "\n## 逐部分点评\n\n"
        for section, comments in detailed.items():
            md += f"### {section}\n\n{comments}\n\n"

    return md


if __name__ == "__main__":
    app()
