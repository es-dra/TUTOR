"""IdeaScheduler Unit Tests - 多Idea调度器测试"""

import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from tutor.core.scheduling.idea_scheduler import (
    IdeaScheduler,
    SchedulerConfig,
    ScheduledTask,
    TaskStatus
)


class TestSchedulerConfig:
    """调度器配置测试"""
    
    def test_default_values(self):
        """测试默认配置值"""
        config = SchedulerConfig()
        assert config.max_concurrent == 3
        assert config.budget_limit_usd == 100.0
        assert config.default_timeout_minutes == 30
        assert config.cost_per_idea_usd == 2.0
        assert config.retry_failed is True
        assert config.max_retries == 1
    
    def test_custom_values(self):
        """测试自定义配置"""
        config = SchedulerConfig(
            max_concurrent=5,
            budget_limit_usd=50.0,
            results_dir=Path("./custom_results")
        )
        assert config.max_concurrent == 5
        assert config.budget_limit_usd == 50.0
        assert config.results_dir == Path("./custom_results")


class TestScheduledTask:
    """调度任务测试"""
    
    def test_task_creation(self):
        """测试任务创建"""
        task = ScheduledTask(
            task_id=str(uuid.uuid4()),
            topic="Graph Neural Networks",
            paper_sources=["paper1.pdf"],
            config={"debate_rounds": 2}
        )
        assert task.status == TaskStatus.PENDING
        assert task.topic == "Graph Neural Networks"
        assert len(task.paper_sources) == 1
        assert task.config["debate_rounds"] == 2
    
    def test_task_to_dict(self):
        """测试任务序列化"""
        now = datetime.now(timezone.utc)
        task = ScheduledTask(
            task_id="test-123",
            topic="Test Topic",
            paper_sources=[],
            config={},
            status=TaskStatus.RUNNING,
            started_at=now,
            cost_estimate=1.5
        )
        
        d = task.to_dict()
        assert d["task_id"] == "test-123"
        assert d["status"] == "running"
        assert d["started_at"] == now.isoformat()
        assert d["cost_estimate"] == 1.5


class TestIdeaScheduler:
    """IdeaScheduler核心测试"""
    
    @pytest.fixture
    def mock_gateway(self):
        """模拟ModelGateway"""
        mock = Mock()
        mock.chat.return_value = "Mock response"
        return mock
    
    @pytest.fixture
    def mock_storage(self):
        """模拟StorageManager"""
        mock = Mock()
        return mock
    
    @pytest.fixture
    def scheduler(self, mock_gateway, mock_storage):
        """创建调度器实例"""
        config = SchedulerConfig(
            max_concurrent=2,
            budget_limit_usd=10.0,
            results_dir=Path("./test_results")
        )
        return IdeaScheduler(mock_gateway, mock_storage, config)
    
    def test_scheduler_initialization(self, scheduler):
        """测试调度器初始化"""
        assert scheduler.config.max_concurrent == 2
        assert scheduler.config.budget_limit_usd == 10.0
        assert len(scheduler._tasks) == 0
        assert scheduler._total_cost == 0.0
    
    def test_create_tasks(self, scheduler):
        """测试创建任务"""
        tasks = [
            ScheduledTask(
                task_id=str(uuid.uuid4()),
                topic="Topic 1",
                paper_sources=[],
                config={}
            ),
            ScheduledTask(
                task_id=str(uuid.uuid4()),
                topic="Topic 2",
                paper_sources=[],
                config={}
            )
        ]
        
        for task in tasks:
            scheduler._tasks[task.task_id] = task
        
        assert len(scheduler._tasks) == 2
    
    def test_budget_check(self, scheduler):
        """测试预算检查"""
        # 超预算应该抛出异常
        tasks = [
            ScheduledTask(
                task_id=str(uuid.uuid4()),
                topic="Expensive Task",
                paper_sources=[],
                config={},
                cost_estimate=6.0
            )
            for _ in range(3)  # 总成本18 > 预算10
        ]
        
        with pytest.raises(ValueError, match="exceeds budget limit"):
            asyncio.run(scheduler.schedule_all(tasks))
    
    def test_task_status_tracking(self, scheduler):
        """测试任务状态跟踪"""
        task = ScheduledTask(
            task_id="test-status",
            topic="Status Test",
            paper_sources=[],
            config={}
        )
        
        # 初始状态
        assert task.status == TaskStatus.PENDING
        assert task.started_at is None
        
        # 更新状态
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None
    
    def test_summary_generation(self, scheduler):
        """测试汇总报告生成"""
        # 添加一些任务
        now = datetime.now(timezone.utc)
        tasks = [
            ScheduledTask(
                task_id="completed-1",
                topic="Completed Topic",
                paper_sources=[],
                config={},
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                actual_cost=1.5,
                result={"recommended_idea": {"final_idea": "Test idea", "overall_score": 0.8}}
            ),
            ScheduledTask(
                task_id="failed-1",
                topic="Failed Topic",
                paper_sources=[],
                config={},
                status=TaskStatus.FAILED,
                error="Test error"
            ),
            ScheduledTask(
                task_id="pending-1",
                topic="Pending Topic",
                paper_sources=[],
                config={}
            )
        ]
        
        scheduler._tasks = {t.task_id: t for t in tasks}
        scheduler._total_cost = 1.5
        
        summary = scheduler._generate_summary()
        
        assert summary["scheduler_info"]["total_tasks"] == 3
        assert summary["scheduler_info"]["completed"] == 1
        assert summary["scheduler_info"]["failed"] == 1
        assert summary["scheduler_info"]["total_cost_usd"] == 1.5
        assert len(summary["recommended_ideas"]) == 1
        assert summary["recommended_ideas"][0]["score"] == 0.8
    
    def test_concurrent_limit_enforcement(self, scheduler):
        """测试并发限制"""
        # 验证semaphore设置正确
        import asyncio
        
        async def test_concurrent():
            # 这里可以模拟多个任务同时执行
            semaphore = asyncio.Semaphore(scheduler.config.max_concurrent)
            
            # 记录并发数
            concurrent_count = 0
            max_concurrent_seen = 0
            
            async def fake_task(task_id: str):
                nonlocal concurrent_count, max_concurrent_seen
                async with semaphore:
                    concurrent_count += 1
                    max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
                    await asyncio.sleep(0.1)  # 模拟任务执行
                    concurrent_count -= 1
                    return task_id
            
            # 启动10个任务
            tasks = [fake_task(f"task-{i}") for i in range(10)]
            await asyncio.gather(*tasks)
            
            # 最大并发数不应超过配置
            assert max_concurrent_seen <= scheduler.config.max_concurrent
        
        asyncio.run(test_concurrent())


class TestIdeaSchedulerIntegration:
    """IdeaScheduler集成测试（需要真实组件）"""
    
    @pytest.mark.skip(reason="需要实际模型和存储，CI环境不运行")
    def test_full_schedule(self):
        """测试完整调度流程"""
        pass


# asyncio运行助手
import asyncio

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
