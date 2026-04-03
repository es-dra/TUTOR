"""TUTOR Terminal UI - 交互式终端界面

基于Rich的交互式TUI，提供完整的工作流生命周期管理。

功能：
- 仪表盘：项目概览、最近运行、系统状态
- 工作流执行：交互式选择和运行工作流
- 运行管理：查看状态、查看输出、取消运行
- 配置管理：查看和修改配置

使用方式：
    tutor tui              # 启动交互式界面
    tutor tui --dashboard  # 直接显示仪表盘
    tutor tui --run idea   # 直接进入IdeaFlow
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TUIState:
    """TUI全局状态"""

    def __init__(self):
        self.current_screen: str = "dashboard"
        self.selected_run: Optional[str] = None
        self.message: Optional[str] = None
        self.projects_dir: Optional[Path] = None
        self._runs: List[Dict[str, Any]] = []

    def add_run(self, run_data: Dict[str, Any]) -> None:
        self._runs.append(run_data)

    def get_runs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            return [r for r in self._runs if r.get("status") == status]
        return self._runs

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        for r in self._runs:
            if r.get("run_id") == run_id:
                return r
        return None

    def update_run(self, run_id: str, **kwargs) -> None:
        for r in self._runs:
            if r.get("run_id") == run_id:
                r.update(kwargs)
                return


class DashboardRenderer:
    """仪表盘渲染"""

    WORKFLOW_INFO = {
        "idea": {"icon": "💡", "name": "IdeaFlow", "desc": "研究想法生成与多角色辩论"},
        "experiment": {"icon": "🧪", "name": "ExperimentFlow", "desc": "实验执行与结果收集"},
        "review": {"icon": "📝", "name": "ReviewFlow", "desc": "论文评审与分析"},
        "write": {"icon": "✍️", "name": "WriteFlow", "desc": "论文撰写与润色"},
        "latex": {"icon": "📄", "name": "LaTeXFlow", "desc": "LaTeX论文生成与编译"},
        "adversarial_review": {"icon": "⚔️", "name": "AdversarialReview", "desc": "对抗式论文评审"},
    }

    @staticmethod
    def render(console, state: TUIState) -> None:
        """渲染仪表盘"""
        try:
            from rich.console import Console as RichConsole
            from rich.table import Table
            from rich.panel import Panel
            from rich.columns import Columns
            from rich.text import Text
        except ImportError:
            print("Rich not installed. Install with: pip install rich")
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Header
        header = Text()
        header.append("🧠 TUTOR", style="bold cyan")
        header.append("  Intelligent Research Automation\n", style="dim")
        header.append(f"   {now}", style="dim")

        console.print(Panel(header, border_style="cyan", title="Dashboard"))

        # Stats
        runs = state.get_runs()
        stats_data = [
            ("Total Runs", str(len(runs)), "white"),
            ("Completed", str(len(state.get_runs("completed"))), "green"),
            ("Running", str(len(state.get_runs("running"))), "yellow"),
            ("Failed", str(len(state.get_runs("failed"))), "red"),
        ]
        stats_table = Table(show_header=False, box=None, padding=(0, 2))
        for label, value, color in stats_data:
            stats_table.add_column()
        stats_table.add_row(
            *[f"[{c}]{v}[/{c}]" for _, v, c in stats_data]
        )
        stats_table.add_row(
            *["[dim]" + l + "[/dim]" for l, _, _ in stats_data]
        )
        console.print(stats_table)
        console.print()

        # Workflow catalog
        console.print("[bold]Available Workflows[/bold]\n")
        wf_table = Table(show_header=True, header_style="bold")
        wf_table.add_column("Workflow", style="cyan", width=25)
        wf_table.add_column("Description", style="dim", width=45)
        wf_table.add_column("Runs", justify="right", width=8)

        info = DashboardRenderer.WORKFLOW_INFO
        for wf_type, wf_info in info.items():
            count = len([r for r in runs if r.get("workflow_type") == wf_type])
            wf_table.add_row(
                f"{wf_info['icon']}  {wf_info['name']}",
                wf_info["desc"],
                str(count),
            )

        console.print(wf_table)
        console.print()

        # Recent runs
        if runs:
            console.print("[bold]Recent Runs[/bold]\n")
            recent = sorted(runs, key=lambda r: r.get("started_at", ""), reverse=True)[:5]
            run_table = Table(show_header=True, header_style="bold")
            run_table.add_column("Run ID", style="cyan", width=12)
            run_table.add_column("Type", width=18)
            run_table.add_column("Status", width=12)
            run_table.add_column("Started", style="dim", width=20)

            for r in recent:
                status_color = {"completed": "green", "running": "yellow", "failed": "red"}.get(
                    r.get("status", ""), "white"
                )
                run_table.add_row(
                    r.get("run_id", ""),
                    r.get("workflow_type", ""),
                    f"[{status_color}]{r.get('status', '')}[/{status_color}]",
                    r.get("started_at", "")[:19],
                )
            console.print(run_table)

        # Message
        if state.message:
            console.print(f"\n[yellow]ℹ {state.message}[/yellow]")

        console.print("\n[dim]Commands: [r] Run workflow  [d] Dashboard  [l] List runs  [q] Quit[/dim]")


class RunDetailRenderer:
    """运行详情渲染"""

    @staticmethod
    def render(console, run_data: Dict[str, Any]) -> None:
        try:
            from rich.table import Table
            from rich.panel import Panel
            from rich.syntax import Syntax
            from rich.tree import Tree
        except ImportError:
            print("Rich not installed")
            return

        # Info panel
        info_lines = [
            f"[bold]Run ID:[/bold]       {run_data.get('run_id', 'N/A')}",
            f"[bold]Type:[/bold]         {run_data.get('workflow_type', 'N/A')}",
            f"[bold]Status:[/bold]       {run_data.get('status', 'N/A')}",
            f"[bold]Started:[/bold]      {run_data.get('started_at', 'N/A')}",
        ]
        if run_data.get("completed_at"):
            info_lines.append(f"[bold]Completed:[/bold]    {run_data['completed_at']}")
        if run_data.get("error"):
            info_lines.append(f"[bold red]Error:[/bold red]     {run_data['error']}")

        console.print(Panel("\n".join(info_lines), title="Run Details", border_style="blue"))

        # Output
        output = run_data.get("output") or run_data.get("result")
        if output:
            console.print("\n[bold]Output:[/bold]\n")
            if isinstance(output, dict):
                for k, v in output.items():
                    console.print(f"  [cyan]{k}:[/cyan] {str(v)[:200]}")
            else:
                console.print(str(output)[:1000])

        console.print("\n[dim][b] Back to dashboard  [q] Quit[/dim]")


class WorkflowRunner:
    """工作流执行器（TUI集成）"""

    def __init__(self, console, state: TUIState):
        self.console = console
        self.state = state

    def run_workflow(self, workflow_type: str, params: Dict[str, Any]) -> Optional[str]:
        """启动工作流执行"""
        import uuid
        run_id = str(uuid.uuid4())[:8]

        run_data = {
            "run_id": run_id,
            "workflow_type": workflow_type,
            "status": "pending",
            "params": params,
            "started_at": datetime.now(timezone.utc).isoformat() + "Z",
        }
        self.state.add_run(run_data)

        try:
            run_data["status"] = "running"
            self.state.update_run(run_id, status="running")

            # Import and run the appropriate workflow
            result = self._execute(workflow_type, params, run_id)

            run_data["status"] = "completed"
            run_data["completed_at"] = datetime.now(timezone.utc).isoformat() + "Z"
            run_data["result"] = result
            self.state.update_run(**run_data)

            self.console.print(f"\n[green]✅ Workflow '{workflow_type}' completed ({run_id})[/green]")
            return run_id

        except Exception as e:
            run_data["status"] = "failed"
            run_data["error"] = str(e)
            run_data["completed_at"] = datetime.now(timezone.utc).isoformat() + "Z"
            self.state.update_run(**run_data)
            self.console.print(f"\n[red]❌ Workflow failed: {e}[/red]")
            return run_id

    def _execute(self, workflow_type: str, params: Dict, run_id: str) -> Dict:
        """实际执行工作流（占位，待与WorkflowEngine集成）"""
        try:
            from rich.progress import Progress, SpinnerColumn, TextColumn

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console,
            ) as progress:
                progress.add_task(f"Running {workflow_type}...", total=None)

                # Placeholder — actual integration will call WorkflowEngine
                import time
                time.sleep(1)

        except ImportError:
            pass

        return {"message": f"Placeholder result for {workflow_type}", "run_id": run_id}


class InteractiveTUI:
    """交互式TUI主循环"""

    def __init__(self):
        self.state = TUIState()
        self._console = None
        self._runner = None

    def _get_console(self):
        if self._console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                import sys
                self._console = type("Console", (), {"print": lambda *a, **kw: print(*a)})()
        return self._console

    def _get_runner(self):
        if self._runner is None:
            self._runner = WorkflowRunner(self._get_console(), self.state)
        return self._runner

    def run(self, start_screen: str = "dashboard") -> None:
        """启动TUI主循环"""
        console = self._get_console()

        try:
            from rich.prompt import Prompt, Confirm
        except ImportError:
            print("Rich not installed. Install with: pip install rich")
            print("TUI requires: pip install rich")
            return

        screen = start_screen

        while True:
            if screen == "dashboard":
                DashboardRenderer.render(console, self.state)
                choice = Prompt.ask(
                    "\n[bold]Action[/bold]",
                    choices=["r", "l", "d", "q"],
                    default="q",
                )
                if choice == "r":
                    screen = "run_select"
                elif choice == "l":
                    screen = "list_runs"
                elif choice == "d":
                    continue  # re-render
                elif choice == "q":
                    break

            elif screen == "run_select":
                console.print("\n[bold]Select Workflow[/bold]\n")
                info = DashboardRenderer.WORKFLOW_INFO
                for i, (wf_type, wf_info) in enumerate(info.items()):
                    console.print(f"  [cyan]{i + 1}[/cyan]. {wf_info['icon']}  {wf_info['name']} — {wf_info['desc']}")

                choice = Prompt.ask(
                    "\n[bold]Choose workflow[/bold] (number or name, q=back)",
                    default="q",
                )

                if choice == "q":
                    screen = "dashboard"
                    continue

                # Map choice to workflow type
                wf_types = list(info.keys())
                if choice.isdigit() and 1 <= int(choice) <= len(wf_types):
                    selected = wf_types[int(choice) - 1]
                elif choice in wf_types:
                    selected = choice
                else:
                    console.print(f"[red]Unknown workflow: {choice}[/red]")
                    continue

                screen = "run_params"
                self.state.message = f"Selected: {info[selected]['name']}"

            elif screen == "run_params":
                console.print("\n[bold]Workflow Parameters[/bold]")
                console.print("[dim]Press Enter for defaults[/dim]\n")

                topic = Prompt.ask("Topic / Research question")
                description = Prompt.ask("Description", default="")

                self._get_runner().run_workflow(
                    self.state.message.split(": ")[1].strip().split("—")[0].strip() if self.state.message else "idea",
                    {"topic": topic, "description": description},
                )
                screen = "dashboard"

            elif screen == "list_runs":
                runs = self.state.get_runs()
                if not runs:
                    console.print("\n[yellow]No runs yet.[/yellow]")
                else:
                    console.print(f"\n[bold]All Runs ({len(runs)})[/bold]\n")
                    for r in runs:
                        status_style = {"completed": "green", "running": "yellow", "failed": "red"}.get(
                            r.get("status", ""), "white"
                        )
                        console.print(
                            f"  [{status_style}]{r.get('run_id', '')}[/{status_style}]  "
                            f"{r.get('workflow_type', '')}  —  {r.get('status', '')}  "
                            f"[dim]{r.get('started_at', '')[:19]}[/dim]"
                        )

                Prompt.ask("\nPress Enter to continue", default="")
                screen = "dashboard"

        console.print("\n[dim]Goodbye! 👋[/dim]")


def run_tui(start_screen: str = "dashboard") -> None:
    """启动TUI"""
    tui = InteractiveTUI()
    tui.run(start_screen=start_screen)


__all__ = [
    "InteractiveTUI",
    "TUIState",
    "DashboardRenderer",
    "RunDetailRenderer",
    "WorkflowRunner",
    "run_tui",
]
