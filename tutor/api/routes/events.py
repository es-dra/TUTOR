"""SSE event stream endpoint."""

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from ...api.sse.events import broadcaster

router = APIRouter()


@router.get("/")
async def event_stream(request: Request):
    """Server-Sent Events stream endpoint.

    Clients connect to receive real-time updates about workflow runs.
    Events: workflow_started, step_completed, log, workflow_finished
    """
    queue = await broadcaster.connect()

    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Wait for next event with timeout to allow disconnect check
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield broadcaster.format_sse(msg)
                except asyncio.TimeoutError:
                    # Send comment to keep connection alive (optional)
                    yield ": keep-alive\n\n"
        finally:
            await broadcaster.disconnect(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
