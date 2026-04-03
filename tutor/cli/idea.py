"""IdeaFlow CLI - 研究想法生成与管理

完整实现Idea生成工作流，包括：
- 文献加载与验证
- AI分析 + 多角色辩论
- 评估与排序
- 输出Markdown提案
"""

import sys
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel

from tutor.core.workflow.idea import IdeaFlow
from tutor.core.storage import StorageManager
from tutor.core.model import ModelGateway
from tutor.config.loader import load_config
from tutor.core.scheduling.idea_scheduler import IdeaScheduler, SchedulerConfig, ScheduledTask
import uuid

# 创建Rich控制台
console = Console()

# 创建Typer应用
app = typer.Typer(
    name="Idea Generation",
    help="Idea生成工作流 - 基于文献的自动化研究想法生成",
    no_args_is_help=True
)


@app.command()
def generate(
    input: str = typer.Argument(
        ...,
        help="研究方向描述或参考文献路径（支持PDF文件或目录）"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="输出目录（默认：./output/ideas/{timestamp}）"
    ),
    keywords: Optional[str] = typer.Option(
        None,
        "--keywords", "-k",
        help="关键词列表，逗号分隔（如：'super-resolution, image quality'）"
    ),
    max_ideas: int = typer.Option(
        10,
        "--max-ideas", "-m",
        help="最大生成想法数量"
    ),
    debate_rounds: int = typer.Option(
        2,
        "--debate-rounds", "-d",
        help="辩论轮数（1-3轮）"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="显示详细日志"
    )
):
    """生成研究想法（完整工作流）

    执行完整流程：文献加载 → AI分析 → 多角色辩论 → 评估 → 排序输出

    示例:
        tutor idea generate "paper.pdf" --keywords "ASISR, image restoration"
        tutor idea generate "研究方向描述" --max-ideas 5 --debate-rounds 1
    """
    try:
        # 1. 加载配置
        with console.status("[bold blue]加载配置...", spinner="dots"):
            config = load_config()
            # 确定存储基础路径（用于 workflow 和 storage_manager）
            storage_base = output or Path(config.get("storage", {}).get("project_dir", "./data/workflows"))
            storage_manager = StorageManager(config, storage_base)
            storage_manager.initialize()
            model_gateway = ModelGateway(config)

        console.print("[✅] 配置加载完成", style="green")

        # 2. 初始化输出目录
        if output is None:
            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output = Path(f"./output/ideas/{timestamp}")
        output.mkdir(parents=True, exist_ok=True)

        console.print(f"[📁] 输出目录: [cyan]{output}[/cyan]")

        # 3. 创建IdeaFlow工作流
        with console.status("[bold blue]初始化工作流...", spinner="dots"):
            workflow = IdeaFlow(
                config=config,
                model_gateway=model_gateway,
                storage_manager=storage_manager,
                max_ideas=max_ideas,
                debate_rounds=debate_rounds,
                output_dir=output
            )

        console.print("[✅] 工作流初始化完成", style="green")

        # 4. 执行工作流（带实时进度显示）
        console.print(Panel.fit(
            f"[bold]输入:[/bold] {input}\n"
            f"[bold]关键词:[/bold] {keywords or '无'}\n"
            f"[bold]最大想法数:[/bold] {max_ideas}\n"
            f"[bold]辩论轮数:[/bold] {debate_rounds}",
            title="🧠 IdeaFlow 工作流启动",
            border_style="blue"
        ))

        # 使用Rich进度条显示执行状态
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]执行中...", total=None)

            try:
                # 执行工作流
                result = workflow.run(
                    input_source=input,
                    keywords=keywords.split(",") if keywords else []
                )

                progress.update(task, completed=True, description="[green]完成")

                # 5. 显示结果摘要
                _display_results(result, console, output)

                # 6. 保存工作流状态
                _save_checkpoint(workflow, output, storage_manager)

                console.print("\n[🎉] Idea生成完成！", style="bold green")
                console.print(f"📄 提案文档: {output / 'research_proposal.md'}")
                console.print(f"📊 统计数据: {output / 'statistics.json'}")

            except Exception as e:
                progress.update(task, completed=True, description="[red]失败")
                console.print(f"\n[❌] 工作流执行失败: {e}", style="bold red")
                if verbose:
                    console.print_exception()
                raise typer.Exit(code=1)

    except FileNotFoundError as e:
        console.print(f"[❌] 文件错误: {e}", style="bold red")
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[❌] 参数错误: {e}", style="bold red")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        console.print("\n[⚠️]  用户中断执行", style="yellow")
        raise typer.Exit(code=130)
    except Exception as e:
        console.print(f"[❌] 未知错误: {e}", style="bold red")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)


@app.command()
def list(
    limit: int = typer.Option(20, "--limit", "-l", help="显示数量限制"),
    sort_by: str = typer.Option("score", "--sort", "-s", help="排序字段: score, date")
):
    """列出所有已生成的idea"""
    try:
        config = load_config()
        storage = StorageManager(config)
        storage.initialize()

        # 从存储中获取idea元数据
        results = storage.list("idea", limit=limit)

        if not results:
            console.print("[ℹ️]  暂未生成任何idea", style="blue")
            return

        # 创建表格显示
        table = Table(title="已生成的研究想法")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("标题", style="white")
        table.add_column("评估分数", justify="right", style="green")
        table.add_column("标签", style="yellow")
        table.add_column("创建时间", style="dim")

        for item in sorted(results, key=lambda x: x.get("metadata", {}).get("created_at", ""), reverse=True):
            meta = item.get("metadata", {})
            score = meta.get("score", "N/A")
            table.add_row(
                meta.get("id", "N/A")[:8],
                meta.get("title", "Untitled")[:50] + ("..." if len(meta.get("title", "")) > 50 else ""),
                f"{score:.2f}" if isinstance(score, (int, float)) else str(score),
                ", ".join(meta.get("tags", [])[:3]),
                meta.get("created_at", "N/A")[:19]
            )

        console.print(table)

    except Exception as e:
        console.print(f"[❌] 列出idea失败: {e}", style="bold red")


@app.command()
def show(
    idea_id: str = typer.Argument(..., help="Idea ID"),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="导出到文件（Markdown格式）"
    )
):
    """显示单个idea的详细信息"""
    try:
        config = load_config()
        storage = StorageManager(config)
        storage.initialize()

        # 从存储加载idea
        item = storage.load("idea", idea_id)
        if not item:
            console.print(f"[❌] 未找到ID为 {idea_id} 的idea", style="bold red")
            raise typer.Exit(code=1)

        data = item.get("data", {})
        meta = item.get("metadata", {})

        # 显示详细信息
        console.print(Panel.fit(
            f"[bold]ID:[/bold] {meta.get('id')}\n"
            f"[bold]标题:[/bold] {meta.get('title', 'N/A')}\n"
            f"[bold]分数:[/bold] {meta.get('score', 'N/A')}\n"
            f"[bold]创建时间:[/bold] {meta.get('created_at', 'N/A')}",
            title="Idea详情",
            border_style="green"
        ))

        # 显示描述
        console.print("\n[bold]📝 描述:[/bold]")
        console.print(data.get("description", "无描述"))

        # 显示创新点
        innovations = data.get("innovations", [])
        if innovations:
            console.print("\n[bold]💡 创新点:[/bold]")
            for i, inn in enumerate(innovations, 1):
                console.print(f"  {i}. {inn}")

        # 显示评估
        evaluation = data.get("evaluation", {})
        if evaluation:
            console.print("\n[bold]📊 评估结果:[/bold]")
            for dim, score in evaluation.items():
                console.print(f"  {dim}: {score:.2f}")

        # 显示辩论记录（如果存在）
        debate_log = data.get("debate_log", [])
        if debate_log:
            console.print("\n[bold]🗣️  辩论记录:[/bold]")
            for entry in debate_log[:5]:  # 只显示前5轮
                console.print(f"  [{entry.get('round', '?')}] {entry.get('speaker', '?')}: {entry.get('content', '')[:100]}...")
            if len(debate_log) > 5:
                console.print(f"  ... 还有 {len(debate_log) - 5} 轮辩论")

        # 导出到文件
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            md_content = _generate_markdown(data, meta)
            output_file.write_text(md_content, encoding="utf-8")
            console.print(f"\n[✅] 已导出到: {output_file}", style="green")

    except Exception as e:
        console.print(f"[❌] 查看idea失败: {e}", style="bold red")


def _display_results(result: dict, console: Console, output: Path):
    """显示工作流执行结果"""
    console.print("\n[bold]📊 工作流执行结果[/bold]")
    console.print("─" * 50)

    stats = result.get("statistics", {})
    total_ideas = stats.get("total_ideas_generated", 0)
    debate_rounds = stats.get("debate_rounds_completed", 0)
    duration = stats.get("total_duration_seconds", 0)

    console.print(f"💡 生成想法数量: [bold cyan]{total_ideas}[/bold cyan]")
    console.print(f"🗣️  完成辩论轮数: [bold cyan]{debate_rounds}[/bold cyan]")
    console.print(f"⏱️  总耗时: [bold cyan]{duration:.1f}秒[/bold cyan]")

    # 显示top ideas
    ideas = result.get("ideas", [])
    if ideas:
        console.print("\n[bold]🏆 Top 5 想法:[/bold]")
        for i, idea in enumerate(ideas[:5], 1):
            console.print(
                f"  {i}. [cyan]{idea.get('title', 'Untitled')}[/cyan]\n"
                f"     分数: [green]{idea.get('score', 0):.2f}[/green] | "
                f"标签: [yellow]{', '.join(idea.get('tags', []))}[/yellow]"
            )


def _save_checkpoint(workflow: IdeaFlow, output: Path, storage: StorageManager):
    """保存工作流检查点"""
    try:
        checkpoint_file = output / "checkpoint.json"
        if hasattr(workflow, "get_checkpoint"):
            checkpoint = workflow.get_checkpoint()
            import json
            checkpoint_file.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False))
    except Exception as e:
        console.print(f"[⚠️]  保存检查点失败（不影响主流程）: {e}", style="yellow")


def _generate_markdown(data: dict, meta: dict) -> str:
    """生成Idea的Markdown格式导出"""
    md = f"""# {meta.get('title', '研究想法')}

**ID**: {meta.get('id')}
**分数**: {meta.get('score', 'N/A')}
**标签**: {', '.join(meta.get('tags', []))}
**创建时间**: {meta.get('created_at')}

## 描述

{data.get('description', '无描述')}

## 创新点

"""
    for i, inn in enumerate(data.get("innovations", []), 1):
        md += f"{i}. {inn}\n"

    md += "\n## 评估结果\n\n"
    for dim, score in data.get("evaluation", {}).items():
        md += f"- **{dim}**: {score:.2f}\n"

    return md


@app.command(name="schedule")
def schedule_batch(
    topics_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="包含多个研究主题的文本文件（每行一个主题）"
    ),
    papers_dir: Optional[Path] = typer.Option(
        None,
        "--papers", "-p",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="参考论文目录（可选）"
    ),
    max_concurrent: int = typer.Option(
        2,
        "--concurrent", "-c",
        help="最大并发任务数"
    ),
    budget: float = typer.Option(
        20.0,
        "--budget", "-b",
        help="总预算限制（美元）"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="调度结果输出目录"
    ),
    debate_rounds: int = typer.Option(
        2,
        "--debate-rounds", "-d",
        help="每个Idea的辩论轮数"
    )
):
    """批量调度多个IdeaFlow工作流（并行执行）

    读取主题列表，为每个主题启动独立的IdeaFlow工作流，
    自动管理并发和预算，最后生成综合报告。

    示例:
        tutor idea schedule topics.txt --papers ./references --concurrent 2 --budget 50
    """
    try:
        # 1. 读取主题列表
        console.print("[bold blue]📖 读取研究主题...[/bold blue]")
        topics = []
        with open(topics_file, 'r', encoding='utf-8') as f:
            for line in f:
                topic = line.strip()
                if topic and not topic.startswith('#'):
                    topics.append(topic)
        
        if not topics:
            console.print("[❌] 主题列表为空", style="bold red")
            raise typer.Exit(1)
        
        console.print(f"[✅] 加载了 {len(topics)} 个研究主题")
        for i, topic in enumerate(topics[:5], 1):
            console.print(f"  {i}. {topic}")
        if len(topics) > 5:
            console.print(f"  ... 还有 {len(topics)-5} 个主题")
        
        # 2. 加载配置和初始化组件
        with console.status("[bold blue]加载配置和模型...", spinner="dots"):
            config = load_config()
            storage_manager = StorageManager(config)
            model_gateway = ModelGateway(config)
        
        console.print("[✅] 配置加载完成", style="green")
        
        # 3. 准备调度器配置
        output_dir = output or Path(f"./output/schedule_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 从全局配置中提取scheduler配置
        scheduler_config_dict = config.get("scheduler", {})
        scheduler_config_dict.update({
            "max_concurrent": max_concurrent,
            "budget_limit_usd": budget,
            "results_dir": str(output_dir)
        })
        
        scheduler_config = SchedulerConfig(config_dict=scheduler_config_dict)
        
        # 4. 收集参考论文
        paper_sources = []
        if papers_dir and papers_dir.exists():
            console.print(f"[📚] 扫描参考论文目录: {papers_dir}")
            for pdf_file in papers_dir.glob("*.pdf"):
                paper_sources.append(str(pdf_file))
                console.print(f"  + {pdf_file.name}")
            console.print(f"[✅] 找到 {len(paper_sources)} 篇参考论文")
        
        # 5. 创建调度任务
        console.print("[🏗️] 创建调度任务...")
        tasks = []
        for i, topic in enumerate(topics):
            task = ScheduledTask(
                task_id=str(uuid.uuid4())[:8],
                topic=topic,
                paper_sources=paper_sources.copy(),  # 共享相同参考文献
                config={
                    "debate_rounds": debate_rounds,
                    "max_ideas": 3  # 每个任务生成3个想法即可
                },
                cost_estimate=scheduler_config.cost_per_idea_usd
            )
            tasks.append(task)
        
        console.print(f"[✅] 创建了 {len(tasks)} 个调度任务")
        
        # 6. 显示预算摘要
        total_estimate = sum(t.cost_estimate for t in tasks)
        console.print(Panel.fit(
            f"并发数: [bold]{max_concurrent}[/bold]\n"
            f"总预算: [bold]${budget:.2f}[/bold]\n"
            f"预估成本: [bold]${total_estimate:.2f}[/bold]\n"
            f"剩余预算: [bold]${budget - total_estimate:.2f}[/bold]",
            title="💰 调度配置",
            border_style="yellow"
        ))
        
        if total_estimate > budget:
            console.print("[❌] 预估成本超过预算！请调整任务数量或增加预算", style="bold red")
            raise typer.Exit(1)
        
        # 7. 创建调度器并执行
        scheduler = IdeaScheduler(
            model_gateway=model_gateway,
            storage_manager=storage_manager,
            config=scheduler_config
        )
        
        console.print("\n[🚀] 开始调度执行...", style="bold blue")
        
        # 8. 异步运行调度器
        import asyncio
        summary = asyncio.run(scheduler.schedule_all(tasks))
        
        # 9. 显示调度结果
        _display_scheduler_summary(summary, console, output_dir)
        
        console.print("\n[🎉] 批量调度完成！", style="bold green")
        console.print(f"📁 结果目录: {output_dir}")
        console.print(f"📄 汇总报告: {output_dir / 'scheduler_summary_*.json'.replace('*', datetime.now(timezone.utc).strftime('%Y%m%d'))}")
        
    except FileNotFoundError as e:
        console.print(f"[❌] 文件错误: {e}", style="bold red")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[❌] 参数错误: {e}", style="bold red")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[⚠️]  用户中断调度", style="yellow")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[❌] 调度失败: {e}", style="bold red")
        console.print_exception()
        raise typer.Exit(1)


def _display_scheduler_summary(summary: dict, console: Console, output_dir: Path):
    """显示调度器汇总结果"""
    info = summary.get("scheduler_info", {})
    
    console.print("\n[bold]📊 调度汇总[/bold]")
    console.print("─" * 50)
    console.print(f"总任务数: [cyan]{info.get('total_tasks', 0)}[/cyan]")
    console.print(f"已完成: [green]{info.get('completed', 0)}[/green]")
    console.print(f"失败: [red]{info.get('failed', 0)}[/red]")
    console.print(f"总成本: [yellow]${info.get('total_cost_usd', 0):.2f}[/yellow]")
    console.print(f"剩余预算: [cyan]${info.get('budget_remaining', 0):.2f}[/cyan]")
    
    # 显示推荐想法
    ideas = summary.get("recommended_ideas", [])
    if ideas:
        console.print("\n[bold]🏆 推荐想法（Top 5）[/bold]")
        for i, idea_data in enumerate(ideas[:5], 1):
            console.print(
                f"  {i}. [cyan]{idea_data.get('topic', 'Unknown')}[/cyan]\n"
                f"     [white]{idea_data.get('idea', '')[:80]}...[/white]\n"
                f"     [green]分数: {idea_data.get('score', 0):.2f}[/green]"
            )


if __name__ == "__main__":
    app()
