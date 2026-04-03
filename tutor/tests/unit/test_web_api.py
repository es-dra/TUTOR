"""Web API 单元测试"""

import asyncio
import json
from unittest.mock import patch, AsyncMock

import pytest


class TestEventBroadcaster:
    def setup_method(self):
        from tutor.api.main import EventBroadcaster
        self.broadcaster = EventBroadcaster()

    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self):
        queue = await self.broadcaster.subscribe("run-1")
        await self.broadcaster.emit("run-1", "step", {"name": "init"})
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event["type"] == "step"
        assert event["data"]["name"] == "init"

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        await self.broadcaster.subscribe("run-1")
        await self.broadcaster.unsubscribe("run-1")
        assert "run-1" not in self.broadcaster._subscribers

    @pytest.mark.asyncio
    async def test_emit_complete_unsubscribes(self):
        await self.broadcaster.subscribe("run-1")
        await self.broadcaster.emit_complete("run-1", {"done": True})
        assert "run-1" not in self.broadcaster._subscribers

    @pytest.mark.asyncio
    async def test_emit_nonexistent_run_no_error(self):
        # Should not raise
        await self.broadcaster.emit("nonexistent", "step", {})


class TestPydanticModels:
    def test_run_request_valid_types(self):
        pytest.importorskip("pydantic")
        from tutor.api.main import RunRequest
        req = RunRequest(workflow_type="idea", params={"topic": "test"})
        assert req.workflow_type == "idea"

    def test_run_response_fields(self):
        pytest.importorskip("pydantic")
        from tutor.api.main import RunResponse
        resp = RunResponse(run_id="abc123", status="pending", workflow_type="idea", message="ok")
        assert resp.run_id == "abc123"
