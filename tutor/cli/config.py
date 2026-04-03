"""TUTOR Config CLI - Placeholder

配置管理命令（开发中）
"""

import typer

app = typer.Typer(
    name="config",
    help="配置管理命令（开发中）",
    no_args_is_help=True,
)


@app.command()
def show():
    """显示当前配置"""
    typer.echo("⚠️  config show 命令尚未实现")
    typer.echo("请直接编辑 config/config.yaml 文件")


@app.command()
def validate():
    """验证配置文件"""
    typer.echo("⚠️  config validate 命令尚未实现")


if __name__ == "__main__":
    app()
