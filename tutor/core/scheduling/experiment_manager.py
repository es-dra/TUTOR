"""Async Experiment Manager - Long-running experiment execution with milestone tracking.

Manages long-running experiment tasks as background processes with:
- Milestone tracking (start, progress, completion events)
- JSONL milestone log for audit trail
- Status polling and listing
- Async subprocess execution

Based on RAP's experiment_async_manager but adapted for TUTOR's architecture.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AsyncExperimentManager:
    """
    Manage long-running experiment tasks with milestone tracking.

    Tasks are submitted as shell commands, run as asyncio subprocesses,
    with milestone events recorded to JSONL files for auditability.

    Usage:
        manager = AsyncExperimentManager(project_root="/path/to/project")
        result = await manager.submit(
            command="python scripts/train.py --config config.yaml",
            name="ablation study",
        )
        status = manager.get_status("task_20260327_120000")
    """

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.base_dir = self.project_root / ".tutor" / "async_experiments"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, task_id: str) -> Path:
        d = self.base_dir / task_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_milestone(
        self,
        task_id: str,
        event: str,
        detail: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a milestone event to the task's milestone log."""
        rec = {
            "time": datetime.now(timezone.utc).isoformat() + "Z",
            "event": event,
            "detail": detail,
            "payload": payload or {},
        }
        p = self._task_dir(task_id) / "milestones.jsonl"
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    async def submit(
        self,
        command: str,
        cwd: Optional[str] = None,
        name: str = "experiment",
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Submit an experiment task to run as a background subprocess.

        Args:
            command: Shell command to execute
            cwd: Working directory (defaults to project_root)
            name: Human-readable task name
            env: Additional environment variables

        Returns:
            Task metadata dict with task_id, status, etc.
        """
        task_id = f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
        task_dir = self._task_dir(task_id)
        stdout_file = task_dir / "stdout.log"
        stderr_file = task_dir / "stderr.log"
        work_dir = cwd or str(self.project_root)

        # Merge environment
        full_env = dict(os.environ)
        if env:
            full_env.update(env)

        meta = {
            "task_id": task_id,
            "name": name,
            "command": command,
            "cwd": work_dir,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
            "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
        }
        self._write_json(task_dir / "meta.json", meta)
        self._append_milestone(task_id, "submitted", f"Task submitted: {name}", {"command": command})

        try:
            with open(stdout_file, "wb") as out, open(stderr_file, "wb") as err:
                process = await asyncio.create_subprocess_shell(
                    command,
                    cwd=work_dir,
                    stdout=out,
                    stderr=err,
                    env=full_env,
                )

            self._append_milestone(task_id, "started", f"Subprocess started (PID: {process.pid})", {"pid": process.pid})

            # Wait for completion
            rc = await process.wait()

            # Update meta
            meta["status"] = "completed" if rc == 0 else "failed"
            meta["returncode"] = rc
            meta["updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"
            self._write_json(task_dir / "meta.json", meta)

            self._append_milestone(
                task_id,
                "completed" if rc == 0 else "failed",
                f"Task finished with return code {rc}",
                {"returncode": rc},
            )

            return meta

        except Exception as e:
            meta["status"] = "failed"
            meta["error"] = str(e)
            meta["updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"
            self._write_json(task_dir / "meta.json", meta)
            self._append_milestone(task_id, "failed", f"Task failed with exception: {e}", {"error": str(e)})
            return meta

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """Get the current status of a task."""
        task_dir = self.base_dir / task_id
        meta_file = task_dir / "meta.json"
        if not meta_file.exists():
            return {"error": f"Task not found: {task_id}"}

        meta = json.loads(meta_file.read_text(encoding="utf-8"))

        # Read recent milestones
        milestones: List[Dict[str, Any]] = []
        ms_file = task_dir / "milestones.jsonl"
        if ms_file.exists():
            for line in ms_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    milestones.append(json.loads(line))
        meta["milestones"] = milestones[-20:]  # Last 20 milestones

        return meta

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List all tasks, sorted by creation time (newest first)."""
        metas: List[Dict[str, Any]] = []
        for d in self.base_dir.iterdir() if self.base_dir.exists() else []:
            if not d.is_dir():
                continue
            mf = d / "meta.json"
            if not mf.exists():
                continue
            try:
                metas.append(json.loads(mf.read_text(encoding="utf-8")))
            except Exception:
                continue
        metas.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return metas[:limit]

    def cancel_task(self, task_id: str) -> bool:
        """Mark a task as cancelled (best-effort; subprocess must support SIGTERM)."""
        task_dir = self.base_dir / task_id
        meta_file = task_dir / "meta.json"
        if not meta_file.exists():
            return False

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if meta["status"] not in ("pending", "running"):
            return False

        meta["status"] = "cancelled"
        meta["updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"
        self._write_json(meta_file, meta)
        self._append_milestone(task_id, "cancelled", "Task cancelled by user")
        return True

    def read_output(self, task_id: str, stream: str = "stdout") -> str:
        """Read the stdout or stderr log of a task."""
        task_dir = self.base_dir / task_id
        f = task_dir / f"{'stdout' if stream == 'stdout' else 'stderr'}.log"
        if not f.exists():
            return ""
        return f.read_text(encoding="utf-8", errors="replace")

