"""Events API Routes

提供实时事件流端点：
- GET /api/v1/events/{run_id} - SSE 事件流
"""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from tutor.api.main import broadcaster
from tutor.core.storage.workflow_runs import RunStorage

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def get_run_storage() -> RunStorage:
    """获取运行存储实例"""
    return RunStorage()


@router.get("/{run_id}")
async def event_stream(run_id: str):
    """SSE事件流 — 实时推送工作流进度

    事件类型：
    - started: 工作流开始
    - step: 步骤进度更新
    - llm_call: LLM调用记录（模型/token/延迟）
    - checkpoint: 检查点保存
    - complete: 工作流完成
    - error: 错误事件
    """
    run_storage = get_run_storage()
    run = run_storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    async def generate():
        queue = await broadcaster.subscribe(run_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] in ("complete", "error"):
                        break
                except asyncio.TimeoutError:
                    yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.now(timezone.utc).isoformat() + 'Z'})}\n\n"
        finally:
            await broadcaster.unsubscribe(run_id, queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
