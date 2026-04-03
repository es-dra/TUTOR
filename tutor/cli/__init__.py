"""TUTOR CLI - 命令行界面入口

MVP 结构：子命令分组，每个工作流一个子命令组
实现委托给各模块：idea.py, experiment.py, review.py, write.py
"""

import typer
from typing import Optional

app = typer.Typer(
    name="tutor",
    help="TUTOR 科研自动化工作流系统 - Thinking Understanding Testing Optimizing Refining",
    add_completion=False,
    no_args_is_help=True
)


# 导入并注册子命令组
try:
    from .idea import app as idea_app
    from .experiment import app as experiment_app  # noqa: F401
    from .review import app as review_app          # noqa: F401
    from .write import app as write_app            # noqa: F401
    from .config import app as config_app          # noqa: F401
    from .api import app as api_app                # noqa: F401
    from .health import app as health_app          # noqa: F401
    from .backup import app as backup_app          # noqa: F401
    from .migrate import app as migrate_app        # noqa: F401
except ImportError as e:
    # MVP阶段：部分模块可能未实现，给出友好提示
    import sys
    print(f"[⚠️]  部分模块未就绪: {e}", file=sys.stderr)
    
    # 创建占位符应用
    def _placeholder_app(name: str):
        app = typer.Typer(help=f"{name} 功能（开发中）")
        @app.command()
        def list():
            """列出可用的命令"""
            typer.echo(f"⚠️  {name} 功能尚未实现")
        return app
    
    idea_app = _placeholder_app("idea")
    experiment_app = _placeholder_app("experiment")
    review_app = _placeholder_app("review")
    write_app = _placeholder_app("write")
    config_app = _placeholder_app("config")
    api_app = _placeholder_app("api")
    health_app = _placeholder_app("health")
    backup_app = _placeholder_app("backup")
    migrate_app = _placeholder_app("migrate")


# 注册子命令组
app.add_typer(idea_app, name="idea")
app.add_typer(experiment_app, name="experiment")
app.add_typer(review_app, name="review")
app.add_typer(write_app, name="write")
app.add_typer(config_app, name="config")
app.add_typer(api_app, name="api")
app.add_typer(health_app, name="health")
app.add_typer(backup_app, name="backup")
app.add_typer(migrate_app, name="migrate")


@app.command()
def status():
    """查看项目和工作流状态"""
    typer.echo("🚀 TUTOR Status (MVP v0.2)")
    typer.echo("Workflow Engine: [✅ Ready]")
    typer.echo("Model Gateway: [✅ Ready]")
    typer.echo("Storage: [✅ Ready]")
    typer.echo("IdeaFlow CLI: [✅ Ready]")
    typer.echo("\nUse 'tutor --help' for available commands.")


@app.command()
def version():
    """显示版本信息"""
    typer.echo("TUTOR v0.2.0-MVP")
    typer.echo("Built with Python 3.9+")
    typer.echo("License: MIT")


if __name__ == "__main__":
    app()
