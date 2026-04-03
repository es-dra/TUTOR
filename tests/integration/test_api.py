"""API 集成测试

测试 FastAPI 应用的核心端点：
- 健康检查
- 工作流运行
- 审批系统
- 限流
"""

import pytest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestHealthEndpoints:
    """健康检查端点测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        # 延迟导入避免循环依赖
        from tutor.api.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_health_check(self):
        """测试 /health 端点"""
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_health_live(self):
        """测试 /health/live 端点"""
        response = self.client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    def test_health_ready(self):
        """测试 /health/ready 端点"""
        response = self.client.get("/health/ready")
        assert response.status_code in [200, 503]  # 503 如果未就绪
        data = response.json()
        assert "status" in data
        assert "timestamp" in data


class TestWorkflowEndpoints:
    """工作流端点测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        from tutor.api.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_start_workflow_invalid_type(self):
        """测试无效的工作流类型"""
        response = self.client.post("/run", json={
            "workflow_type": "invalid_type",
            "params": {}
        })
        assert response.status_code == 400
        assert "Invalid workflow_type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_start_workflow_idea_mocked(self):
        """测试启动 idea 工作流（mock 实际执行）"""
        with patch("tutor.api.main._execute_workflow") as mock_execute:
            mock_execute.return_value = None
            response = self.client.post("/run", json={
                "workflow_type": "idea",
                "params": {"papers": ["https://arxiv.org/abs/2301.00001"]}
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
            assert data["workflow_type"] == "idea"
            assert "run_id" in data

    @pytest.mark.asyncio
    async def test_start_workflow_experiment_mocked(self):
        """测试启动 experiment 工作流（mock 实际执行）"""
        with patch("tutor.api.main._execute_workflow") as mock_execute:
            mock_execute.return_value = None
            response = self.client.post("/run", json={
                "workflow_type": "experiment",
                "params": {"idea_id": "test-idea-123"}
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
            assert data["workflow_type"] == "experiment"

    @pytest.mark.asyncio
    async def test_start_workflow_review_mocked(self):
        """测试启动 review 工作流（mock 实际执行）"""
        with patch("tutor.api.main._execute_workflow") as mock_execute:
            mock_execute.return_value = None
            response = self.client.post("/run", json={
                "workflow_type": "review",
                "params": {"paper_path": "/path/to/paper.pdf"}
            })
            assert response.status_code == 200
            data = response.json()
            assert data["workflow_type"] == "review"

    @pytest.mark.asyncio
    async def test_start_workflow_write_mocked(self):
        """测试启动 write 工作流（mock 实际执行）"""
        with patch("tutor.api.main._execute_workflow") as mock_execute:
            mock_execute.return_value = None
            response = self.client.post("/run", json={
                "workflow_type": "write",
                "params": {"outline": {"title": "Test Paper"}}
            })
            assert response.status_code == 200
            data = response.json()
            assert data["workflow_type"] == "write"

    def test_start_workflow_missing_type(self):
        """测试缺少 workflow_type"""
        response = self.client.post("/run", json={
            "params": {}
        })
        assert response.status_code == 422  # Validation error


class TestRunStatusEndpoints:
    """运行状态查询端点测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        from tutor.api.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_get_run_status_not_found(self):
        """测试获取不存在的运行状态"""
        response = self.client.get("/runs/nonexistent-id")
        assert response.status_code == 404

    def test_list_runs(self):
        """测试列出所有运行"""
        response = self.client.get("/runs")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "meta" in data
        assert "total" in data["meta"]
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_list_runs_with_filters(self):
        """测试带过滤条件的列表查询"""
        response = self.client.get("/runs?status=completed&workflow_type=idea&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "meta" in data
        assert "data" in data

    def test_get_stats(self):
        """测试获取统计信息"""
        response = self.client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "total" in data["data"]
        assert "by_status" in data["data"]
        assert "by_type" in data["data"]


class TestRunManagementEndpoints:
    """运行管理端点测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        from tutor.api.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_delete_run_not_found(self):
        """测试删除不存在的运行"""
        response = self.client.delete("/runs/nonexistent-id")
        assert response.status_code == 404

    def test_cancel_run_not_found(self):
        """测试取消不存在的运行"""
        response = self.client.post("/runs/nonexistent-id/cancel")
        assert response.status_code == 404


class TestApprovalEndpoints:
    """审批端点测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        from tutor.api.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_list_approvals(self):
        """测试列出审批请求"""
        response = self.client.get("/approvals")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "approvals" in data

    def test_list_pending_approvals(self):
        """测试列出待审批请求"""
        response = self.client.get("/approvals/pending")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "approvals" in data

    def test_get_approval_not_found(self):
        """测试获取不存在的审批"""
        response = self.client.get("/approvals/nonexistent-id")
        assert response.status_code == 404

    def test_approve_not_found(self):
        """测试批准不存在的审批"""
        response = self.client.post("/approvals/nonexistent-id/approve")
        assert response.status_code == 400

    def test_reject_not_found(self):
        """测试拒绝不存在的审批"""
        response = self.client.post("/approvals/nonexistent-id/reject")
        assert response.status_code == 400


class TestMetricsEndpoint:
    """Prometheus 指标端点测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        from tutor.api.main import create_app
        self.app = create_app()
        # 使用单独进程模式避免事件循环冲突
        self.client = TestClient(self.app)

    def test_metrics_endpoint(self):
        """测试 /metrics 端点"""
        with patch("tutor.api.prometheus.get_metrics") as mock_metrics:
            mock_instance = Mock()
            mock_instance.format_prometheus.return_value = "tutor_uptime_seconds 100.0\n"
            mock_metrics.return_value = mock_instance
            response = self.client.get("/metrics")
            assert response.status_code == 200


class TestCORSHeaders:
    """CORS 跨域请求测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        from tutor.api.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_cors_headers_present(self):
        """测试 CORS 头存在"""
        response = self.client.options(
            "/run",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            }
        )
        # FastAPI CORSMiddleware 会处理 OPTIONS 请求
        assert response.status_code == 200


class TestRateLimiting:
    """限流测试"""

    def setup_method(self):
        """每个测试方法前设置"""
        from tutor.api.main import create_app
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_rate_limit_headers(self):
        """测试限流响应头"""
        # 快速发送多个请求测试限流
        # 注意: 限流基于 IP，实际测试可能受环境影响
        for _ in range(5):
            response = self.client.get("/runs")
            assert response.status_code in [200, 429]
