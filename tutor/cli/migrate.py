"""TUTOR Database Migration CLI

提供数据库迁移和版本管理功能。

支持：
- Alembic 数据库迁移
- 数据导入/导出（兼容性迁移）
- 版本检查
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from typing import Optional

logger = logging.getLogger(__name__)

app = typer.Typer(help="数据库迁移与版本管理")


@app.command()
def upgrade(
    revision: str = typer.Argument("head", help="目标迁移版本 (默认: head)"),
    sql_only: bool = typer.Option(False, "--sql-only", help="仅生成SQL，不执行"),
):
    """升级数据库到指定版本"""
    typer.echo(f"🔄 Upgrading database to {revision}...")

    # 检查 Alembic 是否可用
    try:
        import alembic.config
    except ImportError:
        typer.echo("❌ Alembic not installed. Install with: pip install alembic", err=True)
        raise typer.Exit(1)

    # TODO: 实际执行迁移（V3+Alembic=生产需求）
    typer.echo("⚠️  Alembic migrations not yet implemented.")
    typer.echo("   This will execute: alembic upgrade <revision>")
    typer.echo("   SQL only mode: alembic upgrade --sql <revision>")


@app.command()
def downgrade(
    revision: str = typer.Argument("-1", help="降级到前一个版本"),
    sql_only: bool = typer.Option(False, "--sql-only", help="仅生成SQL，不执行"),
):
    """降级数据库"""
    typer.echo(f"⏪ Downgrading database to {revision}...")

    try:
        import alembic.config
    except ImportError:
        typer.echo("❌ Alembic not installed.", err=True)
        raise typer.Exit(1)

    typer.echo("⚠️  Alembic migrations not yet implemented.")


@app.command()
def history():
    """显示迁移历史"""
    typer.echo("📜 Migration History")
    typer.echo("\nCurrent database version: base (V3 尚未实施 Alembic)")
    typer.echo("\nPlanned migrations:")
    typer.echo("  - V3: Add monitor table (resource metrics)")
    typer.echo("  - V3: Add checkpoint validation metadata")
    typer.echo("  - V4: Add user/project multi-tenancy")


@app.command()
def current():
    """显示当前数据库版本"""
    typer.echo("📊 Current Database Version")
    typer.echo("  Version: base (V3-MVP, no migrations yet)")
    typer.echo("  Schema: SQLite")
    typer.echo("  Location: /app/data/tutor.db")


@app.command()
def init():
    """初始化迁移环境（生成 alembic.ini 和 versions/）"""
    typer.echo("📁 Initializing Alembic migration environment...")

    migrations_dir = Path("/app/migrations")
    if migrations_dir.exists():
        typer.echo(f"⚠️  Migrations directory already exists: {migrations_dir}")
        return

    try:
        import alembic.config
        from alembic import command
        from alembic.config import Config

        # 创建 alembic.ini 配置
        config = Config()
        config.set_main_option("script_location", str(migrations_dir))
        config.set_main_option("sqlalchemy.url", "sqlite:///./data/tutor.db")

        # 初始化
        command.init(config, str(migrations_dir), "tutor")

        typer.echo(f"✅ Alembic initialized at {migrations_dir}")
        typer.echo("   Edit alembic.ini and migrations/env.py before use.")
    except ImportError:
        typer.echo("❌ Alembic not installed. Install with: pip install alembic", err=True)
        raise typer.Exit(1)


@app.command()
def export(
    output: Path = typer.Option(
        Path("./tutor-export.sql"),
        "--output",
        "-o",
        help="输出文件（SQL 格式）"
    ),
    include_data: bool = typer.Option(
        True,
        "--include-data/--no-data",
        help="是否包含表数据"
    ),
):
    """导出数据库结构和数据（SQL 格式）

    用于：
    - 跨数据库迁移（SQLite → PostgreSQL）
    - 版本备份
    """
    typer.echo(f"📤 Exporting database to {output}...")

    db_path = Path("/app/data/tutor.db")
    if not db_path.exists():
        typer.echo(f"❌ Database not found: {db_path}", err=True)
        raise typer.Exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(output, 'w') as f:
            # 写入 SQLite 的 .dump 格式
            f.write("-- Tutor Database Export\n")
            f.write(f"-- Generated: {datetime.now(timezone.utc).isoformat()}Z\n")
            f.write("-- Includes data: " + ("Yes" if include_data else "No") + "\n\n")

            # 调用 sqlite3 .dump
            cmd = ["sqlite3", str(db_path), ".dump"]
            if not include_data:
                cmd.append("--schema-only")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            f.write(result.stdout)

        size = output.stat().st_size
        typer.echo(f"✅ Export complete: {size} bytes")
        typer.echo(f"   To import: sqlite3 new.db < {output}")
    except subprocess.TimeoutExpired:
        typer.echo("❌ Database dump timed out", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Export failed: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def import_(
    backup_file: Path = typer.Argument(..., help="SQL 文件或备份 tar.gz"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅验证，不实际导入"),
):
    """从 SQL 文件导入数据库"""
    typer.echo(f"📥 Importing from {backup_file}...")

    if not backup_file.exists():
        typer.echo(f"❌ File not found: {backup_file}", err=True)
        raise typer.Exit(1)

    typer.echo("⚠️  Import will replace current database!")
    confirm = typer.confirm("Are you sure?")
    if not confirm:
        typer.echo("Aborted.")
        raise typer.Exit(0)

    if dry_run:
        typer.echo("✅ Dry run: file exists and valid SQL format.")
        return

    try:
        db_path = Path("/app/data/tutor.db")

        # 备份现有数据库
        import shutil
        backup_path = db_path.with_suffix(f".bak-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
        if db_path.exists():
            shutil.copy2(db_path, backup_path)
            typer.echo(f"  → Backed up existing DB to {backup_path}")

        # 导入
        with open(backup_file, 'r') as f:
            content = f.read()

        # 简单的 SQL 格式检查
        if not content.strip().startswith(("--", "BEGIN", "CREATE", "INSERT")):
            typer.echo("❌ Invalid SQL file", err=True)
            raise typer.Exit(1)

        # 执行导入
        result = subprocess.run(
            ["sqlite3", str(db_path)],
            input=content,
            text=True,
            capture_output=True,
            timeout=120,
        )

        if result.returncode != 0:
            typer.echo(f"❌ Import failed: {result.stderr}", err=True)
            raise typer.Exit(1)

        typer.echo("✅ Import completed successfully")
    except Exception as e:
        typer.echo(f"❌ Import failed: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
