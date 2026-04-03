"""ExperimentFlow CLI - 自动化实验工作流

根据选定的研究想法，自动复现相关代码、配置实验环境、执行实验并生成结果报告。
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table

from tutor.core.workflow.experiment import ExperimentFlow
from tutor.core.storage import StorageManager
from tutor.core.model import ModelGateway
from tutor.config.loader import load_config

console = Console()
app = typer.Typer(
    name="Experiment",
    help="自动化实验工作流 - 环境检测、代码执行、结果分析",
    no_args_is_help=True
)


@app.command()
def run(
    research_question: str = typer.Argument(
        ...,
        help="研究问题描述（用于指导实验设计）"
    ),
    paper_ids: Optional[str] = typer.Option(
        None,
        "--papers", "-p",
        help="相关论文ID列表（逗号分隔，如：'paper1,paper2'）"
    ),
    constraints: Optional[str] = typer.Option(
        None,
        "--constraints", "-c",
        help="实验约束条件（JSON格式，如：'{\"time_limit_hours\": 24, \"max_trials\": 10}'）"
    ),
    max_iterations: int = typer.Option(
        5,
        "--max-iterations", "-i",
        help="最大实验迭代次数"
    ),
    output_format: str = typer.Option(
        "md",
        "--format", "-f",
        help="输出格式：md（Markdown）或 latex"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="输出目录（默认：./output/experiment/{timestamp}）"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="显示详细日志"
    )
):
    """运行完整实验流程

    执行：环境检测 → 代码准备 → 实验执行 → 结果分析 → 生成报告

    示例:
        tutor experiment run "如何提升ASISR模型的速度？" --max-iterations 3
        tutor experiment run "模型对比实验" --papers "2301.00001,2305.12345" --constraints '{"gpu_memory_gb": 8}'
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

        # 2. 初始化输出目录
        if output is None:
            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output = Path(f"./output/experiment/{timestamp}")
        output.mkdir(parents=True, exist_ok=True)

        console.print(f"[📁] 输出目录: [cyan]{output}[/cyan]")

        # 3. 解析约束条件
        constraints_dict = {}
        if constraints:
            try:
                constraints_dict = json.loads(constraints)
            except json.JSONDecodeError as e:
                console.print(f"[❌] 约束条件JSON格式错误: {e}", style="bold red")
                raise typer.Exit(1)

        # 4. 解析论文ID
        paper_id_list = []
        if paper_ids:
            paper_id_list = [pid.strip() for pid in paper_ids.split(",") if pid.strip()]

        # 5. 创建ExperimentFlow工作流
        with console.status("[bold blue]初始化工作流...", spinner="dots"):
            workflow = ExperimentFlow(
                config=config,
                model_gateway=model_gateway,
                storage_manager=storage_manager,
                research_question=research_question,
                paper_ids=paper_id_list,
                constraints=constraints_dict,
                max_iterations=max_iterations,
                output_format=output_format,
                output_dir=output
            )

        console.print("[✅] 工作流初始化完成", style="green")

        # 6. 显示工作流配置
        console.print(Panel.fit(
            f"[bold]研究问题:[/bold] {research_question}\n"
            f"[bold]论文数量:[/bold] {len(paper_id_list)}\n"
            f"[bold]最大迭代:[/bold] {max_iterations}\n"
            f"[bold]输出格式:[/bold] {output_format}\n"
            f"[bold]约束条件:[/bold] {json.dumps(constraints_dict, indent=2) if constraints_dict else '无'}",
            title="🔬 ExperimentFlow 工作流启动",
            border_style="yellow"
        ))

        # 7. 执行工作流
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]执行中...", total=None)

            try:
                result = workflow.run()
                progress.update(task, completed=True, description="[green]完成")

                # 8. 显示结果摘要
                _display_results(result, console, output)

                # 9. 保存检查点
                _save_checkpoint(workflow, output, storage_manager)

                console.print("\n[🎉] 实验工作流完成！", style="bold green")
                console.print(f"📄 实验报告: {output / 'experiment_report.md'}")
                console.print(f"📊 统计数据: {output / 'statistics.json'}")

            except Exception as e:
                progress.update(task, completed=True, description="[red]失败")
                console.print(f"\n[❌] 工作流执行失败: {e}", style="bold red")
                if verbose:
                    console.print_exception()
                raise typer.Exit(code=1)

    except FileNotFoundError as e:
        console.print(f"[❌] 文件错误: {e}", style="bold red")
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
def list(
    limit: int = typer.Option(20, "--limit", "-l", help="显示数量限制"),
    status: Optional[str] = typer.Option(
        None,
        "--status", "-s",
        help="按状态筛选：completed,failed,running"
    )
):
    """列出所有实验记录"""
    try:
        config = load_config()
        storage = StorageManager(config)
        storage.initialize()

        results = storage.list("experiment", limit=limit)

        if not results:
            console.print("[ℹ️]  暂未找到任何实验记录", style="blue")
            return

        # 过滤状态
        if status:
            results = [r for r in results if r.get("metadata", {}).get("status") == status]

        # 创建表格
        table = Table(title="实验记录")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("研究问题", style="white")
        table.add_column("状态", style="green")
        table.add_column("迭代次数", justify="right")
        table.add_column("完成时间", style="dim")
        table.add_column("最终指标", style="yellow")

        for item in sorted(results, key=lambda x: x.get("metadata", {}).get("created_at", ""), reverse=True):
            meta = item.get("metadata", {})
            data = item.get("data", {})
            status_val = meta.get("status", "unknown")
            stats = data.get("statistics", {})

            status_style = "green" if status_val == "completed" else "red" if status_val == "failed" else "yellow"

            table.add_row(
                meta.get("id", "N/A")[:8],
                meta.get("title", "N/A")[:40] + ("..." if len(meta.get("title", "")) > 40 else ""),
                f"[{status_style}]{status_val}[/{status_style}]",
                str(stats.get("iterations_completed", 0)),
                meta.get("created_at", "N/A")[:19],
                f"{stats.get('final_metric', 'N/A')}"
            )

        console.print(table)

    except Exception as e:
        console.print(f"[❌] 列出实验记录失败: {e}", style="bold red")


@app.command()
def show(
    experiment_id: str = typer.Argument(..., help="实验ID"),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="导出完整报告到文件"
    )
):
    """显示实验详细信息"""
    try:
        config = load_config()
        storage = StorageManager(config)
        storage.initialize()

        item = storage.load("experiment", experiment_id)
        if not item:
            console.print(f"[❌] 未找到ID为 {experiment_id} 的实验", style="bold red")
            raise typer.Exit(1)

        data = item.get("data", {})
        meta = item.get("metadata", {})

        # 显示基本信息
        console.print(Panel.fit(
            f"[bold]ID:[/bold] {meta.get('id')}\n"
            f"[bold]标题:[/bold] {meta.get('title', 'N/A')}\n"
            f"[bold]状态:[/bold] {meta.get('status', 'N/A')}\n"
            f"[bold]创建时间:[/bold] {meta.get('created_at', 'N/A')}",
            title="实验详情",
            border_style="green"
        ))

        # 显示配置
        config_used = data.get("config", {})
        if config_used:
            console.print("\n[bold]⚙️  实验配置:[/bold]")
            for k, v in config_used.items():
                console.print(f"  {k}: {v}")

        # 显示统计信息
        stats = data.get("statistics", {})
        if stats:
            console.print("\n[bold]📊 统计数据:[/bold]")
            console.print(f"  总迭代次数: {stats.get('iterations_completed', 0)}")
            console.print(f"  总耗时: {stats.get('total_duration_seconds', 0):.1f}秒")
            console.print(f"  最终指标: {stats.get('final_metric', 'N/A')}")
            console.print(f"  历史最佳: {stats.get('best_metric', 'N/A')}")

        # 显示迭代历史
        iterations = data.get("iterations", [])
        if iterations:
            console.print("\n[bold]🔄 迭代历史 (最近5次):[/bold]")
            for it in iterations[-5:]:
                console.print(
                    f"  迭代 {it.get('iteration')}: "
                    f"指标={it.get('metric', 'N/A'):.4f}, "
                    f"耗时={it.get('duration_seconds', 0):.1f}s"
                )

        # 导出文件
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            md_content = _generate_experiment_report(data, meta)
            output_file.write_text(md_content, encoding="utf-8")
            console.print(f"\n[✅] 已导出到: {output_file}", style="green")

    except Exception as e:
        console.print(f"[❌] 查看实验失败: {e}", style="bold red")


def _display_results(result: dict, console: Console, output: Path):
    """显示工作流执行结果"""
    console.print("\n[bold]📊 实验执行结果[/bold]")
    console.print("─" * 50)

    stats = result.get("statistics", {})
    iterations = stats.get("iterations_completed", 0)
    duration = stats.get("total_duration_seconds", 0)
    final_metric = stats.get("final_metric", "N/A")
    best_metric = stats.get("best_metric", "N/A")

    console.print(f"🔁 完成迭代: [bold cyan]{iterations}[/bold cyan]")
    console.print(f"⏱️  总耗时: [bold cyan]{duration:.1f}秒[/bold cyan]")
    console.print(f"📈 最终指标: [bold green]{final_metric}[/bold green]")
    console.print(f"🏆 历史最佳: [bold yellow]{best_metric}[/bold yellow]")

    # 显示环境信息
    env_info = result.get("environment_info", {})
    if env_info:
        console.print("\n[bold]💻 环境信息:[/bold]")
        console.print(f"  Python: {env_info.get('python_version', 'N/A')[:50]}")
        console.print(f"  GPU: {'✅ 可用' if env_info.get('gpu_available') else '❌ 不可用'}")
        console.print(f"  磁盘空间: {env_info.get('disk_space_gb', 0):.1f} GB")
        console.print(f"  内存: {env_info.get('memory_gb', 0):.1f} GB")


def _save_checkpoint(workflow: ExperimentFlow, output: Path, storage: StorageManager):
    """保存工作流检查点"""
    try:
        checkpoint_file = output / "checkpoint.json"
        if hasattr(workflow, "get_checkpoint"):
            checkpoint = workflow.get_checkpoint()
            import json
            checkpoint_file.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False))
    except Exception as e:
        console.print(f"[⚠️]  保存检查点失败（不影响主流程）: {e}", style="yellow")


def _generate_experiment_report(data: dict, meta: dict) -> str:
    """生成实验报告的Markdown格式"""
    stats = data.get("statistics", {})
    config_used = data.get("config", {})
    iterations = data.get("iterations", [])

    md = f"""# 实验报告

**实验ID**: {meta.get('id')}
**研究问题**: {meta.get('title', 'N/A')}
**状态**: {meta.get('status', 'N/A')}
**创建时间**: {meta.get('created_at')}

## 实验配置

```json
{json.dumps(config_used, indent=2, ensure_ascii=False)}
```

## 统计数据

- **总迭代次数**: {stats.get('iterations_completed', 0)}
- **总耗时**: {stats.get('total_duration_seconds', 0):.2f} 秒
- **最终指标**: {stats.get('final_metric', 'N/A')}
- **历史最佳指标**: {stats.get('best_metric', 'N/A')}

## 迭代历史

| 迭代 | 指标 | 耗时(秒) | 备注 |
|------|------|----------|------|
"""
    for it in iterations:
        md += f"| {it.get('iteration', 0)} | {it.get('metric', 'N/A'):.4f} | {it.get('duration_seconds', 0):.1f} | {it.get('notes', '')} |\n"

    md += "\n## 环境信息\n\n"
    env = data.get("environment_info", {})
    for k, v in env.items():
        md += f"- **{k}**: {v}\n"

    return md


if __name__ == "__main__":
    app()
