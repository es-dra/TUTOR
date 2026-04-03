"""TUTOR Health Check CLI

提供健康检查和系统监控命令。
"""

import json
import logging
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from typing import Optional

logger = logging.getLogger(__name__)

app = typer.Typer(help="系统健康检查和监控命令")


def check_process(host: str, port: int, timeout: float = 1.0) -> bool:
    """检查端口连通性"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


@app.command()
def check():
    """执行健康检查

    检查：
    - 磁盘空间
    - 数据库连接
    - 配置文件
    - API端口
    """
    typer.echo("🔍 Health Check Report")
    typer.echo(f"Timestamp: {datetime.now(timezone.utc).isoformat()}Z")
    typer.echo()

    checks_passed = 0
    checks_total = 0

    # 1. 检查磁盘空间
    checks_total += 1
    try:
        usage = shutil.disk_usage("/app/data" if Path("/app/data").exists() else ".")
        percent = (usage.used / usage.total) * 100
        if percent < 95:
            typer.echo(f"✅ Disk Space: {percent:.1f}% used (< 95%)")
            checks_passed += 1
        else:
            typer.echo(f"❌ Disk Space: {percent:.1f}% used (CRITICAL > 95%)")
    except Exception as e:
        typer.echo(f"❌ Disk Space: error - {e}")

    # 2. 检查配置文件
    checks_total += 1
    config_path = Path("/app/config.yaml")
    if config_path.exists():
        typer.echo(f"✅ Config: exists at /app/config.yaml")
        checks_passed += 1
    else:
        typer.echo(f"⚠️  Config: not found at /app/config.yaml (using defaults)")

    # 3. 检查数据目录
    checks_total += 1
    data_dir = Path("/app/data")
    if data_dir.exists() and data_dir.is_dir():
        typer.echo(f"✅ Data Dir: /app/data exists")
        checks_passed += 1
    else:
        typer.echo(f"❌ Data Dir: /app/data missing")

    # 4. 检查API端口
    checks_total += 1
    if check_process("localhost", 8000):
        typer.echo(f"✅ API Port: 8000 is listening")
        checks_passed += 1
    else:
        typer.echo(f"⚠️  API Port: 8000 not listening (app may be down)")

    # 5. 检查PostgreSQL
    checks_total += 1
    if check_process("localhost", 5432):
        typer.echo(f"✅ PostgreSQL: port 5432 reachable")
        checks_passed += 1
    else:
        typer.echo(f"❌ PostgreSQL: port 5432 unreachable")

    # 6. 检查Redis
    checks_total += 1
    if check_process("localhost", 6379):
        typer.echo(f"✅ Redis: port 6379 reachable")
        checks_passed += 1
    else:
        typer.echo(f"❌ Redis: port 6379 unreachable")

    # 总结
    typer.echo()
    typer.echo(f"📊 Summary: {checks_passed}/{checks_total} checks passed")

    if checks_passed == checks_total:
        typer.echo("🟢 System is HEALTHY")
        sys.exit(0)
    elif checks_passed >= checks_total * 0.7:
        typer.echo("🟡 System is DEGRADED")
        sys.exit(1)
    else:
        typer.echo("🔴 System is UNHEALTHY")
        sys.exit(2)


@app.command()
def metrics():
    """显示系统指标（JSON格式）"""
    try:
        import psutil
        import shutil
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage_percent": (shutil.disk_usage("/app/data").used / shutil.disk_usage("/app/data").total) * 100 if Path("/app/data").exists() else None,
        }
        typer.echo(json.dumps(data, indent=2))
    except ImportError:
        typer.echo("Error: psutil not installed", err=True)
        sys.exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        sys.exit(1)


@app.command()
def vacuum():
    """执行SQLite数据库VACUMM（如果使用本地SQLite）"""
    typer.echo("🧹 Running database VACUUM...")

    try:
        from tutor.core.storage.sqlite_backend import SQLiteBackend
        from tutor.core.storage.base import StorageManager

        # 默认数据库路径
        db_path = Path("/app/data/tutor.db")

        if not db_path.exists():
            typer.echo(f"⚠️  Database not found at {db_path}, skipping VACUUM")
            return

        backend = SQLiteBackend(str(db_path))
        backend.initialize()
        backend.vacuum()
        backend.optimize()
        backend.close()

        typer.echo("✅ VACUUM completed successfully")
    except Exception as e:
        typer.echo(f"❌ VACUUM failed: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    app()
