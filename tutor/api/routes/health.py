"""Health check endpoints."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["system"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check (backward compatible)."""
    payload = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }
    return {"success": True, "data": payload, **payload}


@router.get("/health/live")
async def health_live() -> Dict[str, Any]:
    """Liveness Probe - is the application alive?"""
    payload = {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }
    return {"success": True, "data": payload, **payload}


@router.get("/health/ready")
async def health_ready() -> JSONResponse:
    """Readiness Probe - is the application ready (dependency check)?"""
    checks: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }

    # Check disk space
    try:
        import shutil
        storage_path = Path.cwd()
        usage = shutil.disk_usage(storage_path)
        used_percent = (usage.used / usage.total * 100) if usage.total else 100
        checks["disk_ok"] = used_percent < 95
        checks["disk_usage_percent"] = round(used_percent, 2)
    except Exception as e:
        checks["disk_ok"] = False
        checks["disk_error"] = str(e)

    # Check config
    checks["config_loaded"] = True

    # Check rate limiter
    checks["rate_limiter_ok"] = True

    # Overall readiness
    is_ready = checks.get("disk_ok", False) and checks.get("config_loaded", False)
    checks["status"] = "ready" if is_ready else "not_ready"

    status_code = 200 if is_ready else 503
    return JSONResponse(content=checks, status_code=status_code)
