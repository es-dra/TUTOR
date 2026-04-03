"""Health check endpoints for TutorClaw API."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from .prometheus import get_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> Dict[str, str]:
    """Liveness probe - checks if the service is running."""
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness() -> Dict[str, Any]:
    """Readiness probe - checks if the service can serve requests."""
    checks: Dict[str, Any] = {}

    # Check SQLite connection
    checks["sqlite"] = await _check_sqlite()

    # Check disk space
    checks["disk_space"] = await _check_disk_space()

    # Check checkpoint directory writable
    checks["checkpoint_writable"] = await _check_checkpoint_writable()

    overall_status = "ready"
    for check_name, check_result in checks.items():
        if check_result.get("status") != "ok":
            overall_status = "degraded"
            break

    return {
        "status": overall_status,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics_prometheus() -> str:
    """Metrics endpoint in Prometheus text format."""
    metrics = get_metrics()
    return metrics.format_prometheus()


@router.get("/metrics/json")
async def metrics_json() -> Dict[str, Any]:
    """Metrics endpoint in JSON format (for debugging)."""
    metrics = get_metrics()
    return metrics.format_json()


async def _check_sqlite() -> Dict[str, Any]:
    """Check if SQLite database is accessible."""
    try:
        # Try to create an in-memory database connection
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT 1")
        conn.close()
        return {"status": "ok", "message": "SQLite connection successful"}
    except Exception as e:
        logger.error(f"SQLite health check failed: {e}")
        return {"status": "error", "message": str(e)}


async def _check_disk_space() -> Dict[str, Any]:
    """Check available disk space."""
    try:
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024**3)
        total_gb = total / (1024**3)

        # Consider degraded if less than 1GB free
        if free_gb < 1.0:
            return {
                "status": "degraded",
                "message": f"Low disk space: {free_gb:.2f}GB free of {total_gb:.2f}GB",
                "free_gb": free_gb,
                "total_gb": total_gb,
            }

        return {
            "status": "ok",
            "message": f"Sufficient disk space: {free_gb:.2f}GB free of {total_gb:.2f}GB",
            "free_gb": free_gb,
            "total_gb": total_gb,
        }
    except Exception as e:
        logger.error(f"Disk space check failed: {e}")
        return {"status": "error", "message": str(e)}


async def _check_checkpoint_writable() -> Dict[str, Any]:
    """Check if checkpoint directory is writable."""
    checkpoint_dir = Path("./checkpoints")
    try:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        test_file = checkpoint_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return {"status": "ok", "message": "Checkpoint directory is writable"}
    except Exception as e:
        logger.error(f"Checkpoint directory check failed: {e}")
        return {"status": "error", "message": str(e)}
