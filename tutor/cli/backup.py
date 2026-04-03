"""TUTOR Backup & Restore CLI

提供数据库和项目数据的备份与恢复功能。
"""

import json
import logging
import os
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import typer
from typing import Optional

logger = logging.getLogger(__name__)

app = typer.Typer(help="数据备份与迁移命令")


def _run_sql_command(sql: str, db_url: Optional[str] = None) -> subprocess.CompletedProcess:
    """执行数据库SQL命令"""
    # 默认数据库路径
    db_path = "/app/data/tutor.db"
    if db_url and db_url.startswith("sqlite://"):
        db_path = db_url[9:]  # 去掉 sqlite:// 前缀

    cmd = ["sqlite3", db_path, sql]
    return subprocess.run(cmd, capture_output=True, text=True)


@app.command()
def create(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="输出文件路径（默认：/app/backups/tutor-YYYY-MM-DD-HHMMSS.tar.gz）"
    ),
    include_workflows: bool = typer.Option(
        True,
        "--include-workflows/--no-include-workflows",
        help="是否包含工作流数据和检查点"
    ),
    include_examples: bool = typer.Option(
        False,
        "--include-examples/--no-include-examples",
        help="是否包含示例项目"
    ),
):
    """创建完整备份

    备份内容包括：
    - SQLite 数据库（元数据 + 检查点）
    - 工作流结果（results/）
    - 配置文件（config/）
    - 用户数据（papers/, experiments/）
    """
    typer.echo("📦 Creating backup...")

    # 确定输出路径
    if output is None:
        backup_dir = Path("/app/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        output = backup_dir / f"tutor-{timestamp}.tar.gz"

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        backup_root = tmp_path / "backup"
        backup_root.mkdir()

        files_backed_up = 0

        # 1. 备份数据库
        typer.echo("  → Backing up database...")
        db_path = Path("/app/data/tutor.db")
        if db_path.exists():
            # 执行 WAL checkpoint 确保数据完整
            _run_sql_command("PRAGMA wal_checkpoint(TRUNCATE);", f"sqlite:///{db_path}")

            # 复制数据库文件（包含 -wal 和 -shm）
            import shutil
            for suffix in ["", "-wal", "-shm"]:
                src = db_path.with_suffix(db_path.suffix + suffix)
                if src.exists():
                    dest = backup_root / src.name
                    shutil.copy2(src, dest)
                    files_backed_up += 1
            typer.echo(f"    ✅ Database ({files_backed_up} files)")
        else:
            typer.echo("    ⚠️  Database not found, skipping")

        # 2. 备份配置
        typer.echo("  → Backing up configuration...")
        config_src = Path("/app/config")
        if config_src.exists():
            config_dest = backup_root / "config"
            import shutil
            shutil.copytree(config_src, config_dest, dirs_exist_ok=True)
            typer.echo("    ✅ Configuration")
        else:
            typer.echo("    ⚠️  Config directory not found")

        # 3. 备份工作流数据
        if include_workflows:
            typer.echo("  → Backing up workflow data...")
            data_dirs = [
                "/app/data/results",
                "/app/data/checkpoints",
                "/app/data/papers",
            ]
            for data_dir in data_dirs:
                src = Path(data_dir)
                if src.exists():
                    relative = src.relative_to("/app")
                    dest = backup_root / relative
                    import shutil
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                    typer.echo(f"    ✅ {relative}")
                else:
                    typer.echo(f"    ⚠️  {data_dir} not found")

        # 4. 备份示例项目
        if include_examples:
            typer.echo("  → Backing up examples...")
            examples_src = Path("/app/examples")
            if examples_src.exists():
                examples_dest = backup_root / "examples"
                import shutil
                shutil.copytree(examples_src, examples_dest, dirs_exist_ok=True)
                typer.echo("    ✅ examples/")
            else:
                typer.echo("    ⚠️  examples/ not found")

        # 5. 创建元数据
        typer.echo("  → Creating manifest...")
        manifest = {
            "backup_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
            "include_workflows": include_workflows,
            "include_examples": include_examples,
            "files": [],
        }

        for file in backup_root.rglob("*"):
            if file.is_file():
                manifest["files"].append({
                    "path": str(file.relative_to(backup_root)),
                    "size": file.stat().st_size,
                })

        manifest_path = backup_root / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        # 6. 打包 tar.gz
        typer.echo("  → Creating archive...")
        with tarfile.open(output, "w:gz") as tar:
            tar.add(backup_root, arcname="backup")

        # 验证备份大小
        backup_size = output.stat().st_size
        typer.echo(f"\n✅ Backup created: {output} ({backup_size / 1024 / 1024:.1f} MB)")
        typer.echo(f"   Total files: {files_backed_up + len(manifest['files'])}")


@app.command()
def restore(
    backup_file: Path = typer.Argument(..., help="备份文件路径（.tar.gz）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="模拟运行，不实际恢复"),
):
    """恢复备份"""
    typer.echo(f"🔧 Restoring from backup: {backup_file}")

    if not backup_file.exists():
        typer.echo(f"❌ Backup file not found: {backup_file}", err=True)
        raise typer.Exit(1)

    # 验证备份
    typer.echo("  → Validating backup...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with tarfile.open(backup_file, "r:gz") as tar:
            # 检查manifest
            try:
                manifest_member = tar.getmember("backup/manifest.json")
                manifest_f = tar.extractfile(manifest_member)
                manifest = json.load(manifest_f)
                typer.echo(f"    ✅ Manifest found, version {manifest.get('backup_version')}")
            except KeyError:
                typer.echo("    ❌ Manifest not found, invalid backup", err=True)
                raise typer.Exit(1)

        if dry_run:
            typer.echo("\n✅ Dry run successful, backup is valid")
            return

        # 停止应用（简化：提示用户）
        typer.echo("\n⚠️  Please stop the Tutor application before restoring!")
        confirm = typer.confirm("Have you stopped the application?")
        if not confirm:
            typer.echo("Aborted. Please stop the app and retry.")
            raise typer.Exit(1)

        # 执行恢复
        typer.echo("  → Extracting backup...")
        with tarfile.open(backup_file, "r:gz") as tar:
            tar.extractall("/app", strip_components=1)  # 提取到 /app，去掉顶层目录

        typer.echo("\n✅ Restore completed successfully")
        typer.echo("   You can now restart the application.")


@app.command()
def list_backups(
    backup_dir: Path = typer.Option(Path("/app/backups"), "--backup-dir", "-d", help="备份目录"),
):
    """列出所有可用备份"""
    if not backup_dir.exists():
        typer.echo(f"Backup directory not found: {backup_dir}")
        return

    backups = sorted(backup_dir.glob("tutor-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not backups:
        typer.echo("No backups found.")
        return

    typer.echo(f"📁 Backups in {backup_dir}:")
    typer.echo()
    typer.echo(f"{'DATE':<20} {'SIZE':<12} {'FILE'}")
    typer.echo("-" * 80)

    for backup in backups[:10]:  # 只显示最近10个
        stat = backup.stat()
        date = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        size_mb = stat.st_size / 1024 / 1024
        typer.echo(f"{date:<20} {size_mb:>8.1f} MB {backup.name}")


if __name__ == "__main__":
    app()
