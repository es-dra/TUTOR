"""SSE event broadcaster for real-time progress updates."""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set, Optional, Any

from ..models import LogEvent, SSEMessage, StepEvent, WorkflowFinishedEvent


class EventBroadcaster:
    """Manages broadcasting events to all connected SSE clients."""

    def __init__(self):
        self.connections: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def connect(self) -> asyncio.Queue:
        """Register a new client connection, return its queue."""
        queue = asyncio.Queue()
        async with self._lock:
            self.connections.add(queue)
        return queue

    async def disconnect(self, queue: asyncio.Queue):
        """Remove a client connection."""
        async with self._lock:
            self.connections.discard(queue)

    async def broadcast(self, sse_message: SSEMessage):
        """Send an event to all connected clients."""
        async with self._lock:
            dead_queues = []
            for queue in self.connections:
                try:
                    await queue.put(sse_message)
                except Exception:
                    dead_queues.append(queue)
            for dead in dead_queues:
                self.connections.discard(dead)

    def format_sse(self, sse_message: SSEMessage) -> str:
        """Format a message as SSE data packet."""
        payload = sse_message.data.copy()
        payload["event"] = sse_message.event
        payload["run_id"] = sse_message.run_id
        return f"data: {json.dumps(payload)}\n\n"


# Global broadcaster instance
broadcaster = EventBroadcaster()


# Convenience functions for common events
async def emit_workflow_started(run_id: str, workflow_name: str, started_at: datetime):
    msg = SSEMessage(
        event="workflow_started",
        run_id=run_id,
        data={"workflow_name": workflow_name, "started_at": started_at.isoformat()},
    )
    await broadcaster.broadcast(msg)


async def emit_step_completed(run_id: str, step_name: str, status: str, message: Optional[str] = None):
    msg = SSEMessage(
        event="step_completed",
        run_id=run_id,
        data={"step_name": step_name, "status": status, "message": message},
    )
    await broadcaster.broadcast(msg)


async def emit_log(run_id: str, level: str, message: str):
    log_event = LogEvent(run_id=run_id, level=level, message=message, timestamp=datetime.now(timezone.utc))
    msg = SSEMessage(
        event="log",
        run_id=run_id,
        data=log_event.dict(),
    )
    await broadcaster.broadcast(msg)


async def emit_workflow_finished(run_id: str, status: str, final_output: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
    msg = SSEMessage(
        event="workflow_finished",
        run_id=run_id,
        data={"status": status, "final_output": final_output, "error": error},
    )
    await broadcaster.broadcast(msg)
