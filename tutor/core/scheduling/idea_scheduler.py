"""IdeaScheduler - 多Idea并行调度器

负责调度多个IdeaFlow工作流的并行执行，管理资源、成本和时间。
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from tutor.core.workflow.idea import IdeaFlow
from tutor.core.model import ModelGateway
from tutor.core.storage import StorageManager
from tutor.core.workflow.base import WorkflowResult

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """调度的任务
    
    表示一个被调度的IdeaFlow工作流实例。
    """
    task_id: str
    topic: str  # 研究主题/方向
    paper_sources: List[str]  # 参考论文列表
    config: Dict[str, Any]  # IdeaFlow配置
    status: TaskStatus = TaskStatus.PENDING
    workflow_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cost_estimate: float = 0.0  # 预估成本
    actual_cost: float = 0.0  # 实际成本
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "topic": self.topic,
            "paper_sources": self.paper_sources,
            "config": self.config,
            "status": self.status.value,
            "workflow_id": self.workflow_id,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "cost_estimate": self.cost_estimate,
            "actual_cost": self.actual_cost
        }


class SchedulerConfig:
    """调度器配置
    
    控制并发度、预算、超时等调度参数。
    
    支持两种初始化方式：
    
    1. 关键字参数::
    
        config = SchedulerConfig(max_concurrent=5, budget_limit_usd=50.0)

    2. 配置字典（向后兼容）::

        config = SchedulerConfig(config_dict={"max_concurrent": 5})
    """
    def __init__(self,
                 config_dict: Dict[str, Any] = None,
                 max_concurrent: int = None,
                 budget_limit_usd: float = None,
                 default_timeout_minutes: int = None,
                 cost_per_idea_usd: float = None,
                 retry_failed: bool = None,
                 max_retries: int = None,
                 results_dir=None):
        # 以 config_dict 为基础，关键字参数覆盖字典值
        base = config_dict or {}
        
        self.max_concurrent = max_concurrent if max_concurrent is not None else int(base.get("max_concurrent", 3))
        self.budget_limit_usd = budget_limit_usd if budget_limit_usd is not None else float(base.get("budget_limit_usd", 100.0))
        self.default_timeout_minutes = default_timeout_minutes if default_timeout_minutes is not None else int(base.get("default_timeout_minutes", 30))
        self.cost_per_idea_usd = cost_per_idea_usd if cost_per_idea_usd is not None else float(base.get("cost_per_idea_usd", 2.0))
        self.retry_failed = retry_failed if retry_failed is not None else bool(base.get("retry_failed", True))
        self.max_retries = max_retries if max_retries is not None else int(base.get("max_retries", 1))
        
        # 结果输出目录
        if results_dir is not None:
            self.results_dir = Path(results_dir)
        else:
            results_dir_val = base.get("results_dir", "./scheduler_results")
            self.results_dir = Path(results_dir_val)
        
        self.results_dir.mkdir(parents=True, exist_ok=True)


class IdeaScheduler:
    """IdeaScheduler - 多Idea并行调度器
    
    负责调度多个IdeaFlow工作流的并行执行，管理资源、成本和时间。
    
    主要功能：
    1. 任务队列管理（优先级、顺序）
    2. 并发控制（线程池管理）
    3. 资源估算（成本、时间）
    4. 进度监控（实时状态）
    5. 结果聚合（综合报告）
    
    使用示例：
    ```python
    config = SchedulerConfig(max_concurrent=2, budget_limit_usd=50.0)
    scheduler = IdeaScheduler(model_gateway, storage_manager, config)
    
    tasks = [
        ScheduledTask(
            task_id=str(uuid.uuid4()),
            topic="Graph Neural Networks for Drug Discovery",
            paper_sources=["paper1.pdf", "https://arxiv.org/abs/2301.00001"],
            config={"debate_rounds": 2}
        ),
        # ...更多任务
    ]
    
    results = await scheduler.schedule_all(tasks)
    ```
    """
    
    def __init__(
        self,
        model_gateway: ModelGateway,
        storage_manager: StorageManager,
        config: Union[SchedulerConfig, Dict[str, Any]] = None
    ):
        """初始化调度器
        
        Args:
            model_gateway: 模型网关实例
            storage_manager: 存储管理器实例
            config: 调度器配置对象或配置字典
        """
        self.model = model_gateway
        self.storage = storage_manager
        
        # 支持传入SchedulerConfig对象或字典
        if isinstance(config, SchedulerConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = SchedulerConfig(config_dict=config)
        else:
            self.config = SchedulerConfig()
        
        # 运行时状态
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._total_cost: float = 0.0
        self._lock = asyncio.Lock()
        
        logger.info(
            f"IdeaScheduler initialized: "
            f"max_concurrent={self.config.max_concurrent}, "
            f"budget_limit=${self.config.budget_limit_usd:.2f}"
        )
    
    async def schedule_all(self, tasks: List[ScheduledTask]) -> Dict[str, Any]:
        """调度所有任务并等待完成
        
        Args:
            tasks: 要调度的任务列表
            
        Returns:
            调度结果汇总
        """
        logger.info(f"Scheduling {len(tasks)} tasks")
        
        # 检查预算
        total_estimate = sum(
            t.cost_estimate or self.config.cost_per_idea_usd for t in tasks
        )
        if total_estimate > self.config.budget_limit_usd:
            raise ValueError(
                f"Total estimated cost (${total_estimate:.2f}) "
                f"exceeds budget limit (${self.config.budget_limit_usd:.2f})"
            )
        
        # 注册任务
        for task in tasks:
            self._tasks[task.task_id] = task
            if task.cost_estimate == 0.0:
                task.cost_estimate = self.config.cost_per_idea_usd
        
        # 启动调度器
        results = await self._run_scheduler()
        
        # 生成汇总报告
        summary = self._generate_summary()
        
        # 保存结果
        summary_file = self.config.results_dir / f"scheduler_summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        import json
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"Scheduler completed. Summary saved to: {summary_file}")
        
        return summary
    
    async def _run_scheduler(self) -> List[Dict[str, Any]]:
        """运行调度器主循环
        
        使用信号量控制并发数，异步执行所有任务。
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        tasks_to_run = list(self._tasks.values())
        results = []
        
        async def run_with_limit(task: ScheduledTask):
            """包装任务执行，控制并发"""
            async with semaphore:
                logger.info(f"Starting task {task.task_id}: {task.topic}")
                try:
                    result = await self._execute_task(task)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Task {task.task_id} failed: {e}")
                    results.append({
                        "task_id": task.task_id,
                        "status": "failed",
                        "error": str(e)
                    })
        
        # 创建所有任务协程
        coroutines = [run_with_limit(task) for task in tasks_to_run]
        
        # 并发执行
        await asyncio.gather(*coroutines, return_exceptions=True)
        
        return results
    
    async def _execute_task(self, task: ScheduledTask) -> Dict[str, Any]:
        """执行单个任务
        
        创建并运行一个IdeaFlow工作流实例。
        """
        async with self._lock:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
        
        try:
            logger.info(f"[Task {task.task_id}] Creating IdeaFlow instance")
            
            # 创建工作流存储路径
            project_dir = Path(f"./projects/idea_scheduler_{task.task_id[:8]}")
            project_dir.mkdir(parents=True, exist_ok=True)
            
            # 构建工作流配置（合并任务特定配置）
            workflow_config = {
                "type": "idea",
                "steps": 6,
                "debate_rounds": task.config.get("debate_rounds", 2),
                "paper_sources": task.paper_sources,
                **task.config  # 允许覆盖默认值
            }
            
            # 实例化IdeaFlow工作流
            workflow = IdeaFlow(
                workflow_id=f"idea_{task.task_id[:8]}",
                config=workflow_config,
                storage_path=project_dir,
                model_gateway=self.model
            )
            
            logger.info(f"[Task {task.task_id}] Running IdeaFlow")
            
            # 在线程池中运行同步的workflow.run()
            result: WorkflowResult = await self._run_workflow_async(workflow)
            
            async with self._lock:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                task.workflow_id = result.workflow_id
                # 提取工作流输出状态
                task.result = result.output
                # 计算实际成本（简化：基于预估）
                task.actual_cost = task.cost_estimate
                self._total_cost += task.actual_cost
            
            logger.info(
                f"[Task {task.task_id}] Completed. "
                f"Cost: ${task.actual_cost:.2f}, "
                f"Duration: {result.duration_seconds:.1f}s"
            )
            
            return task.to_dict()
            
        except Exception as e:
            async with self._lock:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now(timezone.utc)
                task.error = str(e)
            
            logger.error(f"[Task {task.task_id}] Failed: {e}")
            
            raise
    
    async def _run_workflow_async(self, workflow: IdeaFlow) -> WorkflowResult:
        """异步运行工作流
        
        将同步工作流包装为异步执行。
        """
        loop = asyncio.get_event_loop()
        
        def run_sync():
            try:
                return workflow.run()
            except Exception as e:
                logger.error(f"Workflow execution failed: {e}")
                raise
        
        # 在线程池中运行同步代码
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = loop.run_in_executor(executor, run_sync)
            try:
                result = await future
                return result
            except Exception as e:
                raise
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            task.cancel()
            logger.info(f"Task {task_id} cancelled")
            return True
        return False
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if task_id in self._tasks:
            return self._tasks[task_id].to_dict()
        return None
    
    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        return [task.to_dict() for task in self._tasks.values()]
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成调度汇总报告"""
        total_tasks = len(self._tasks)
        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        
        successful_results = [
            t.result for t in self._tasks.values()
            if t.status == TaskStatus.COMPLETED and t.result
        ]
        
        # 提取所有推荐的想法
        all_recommended_ideas = []
        for result in successful_results:
            if "recommended_idea" in result:
                all_recommended_ideas.append({
                    "topic": result.get("topic", "Unknown"),
                    "idea": result["recommended_idea"].get("final_idea", ""),
                    "score": result["recommended_idea"].get("overall_score", 0)
                })
        
        # 按评分排序
        all_recommended_ideas.sort(key=lambda x: x["score"], reverse=True)
        
        summary = {
            "scheduler_info": {
                "total_tasks": total_tasks,
                "completed": completed,
                "failed": failed,
                "total_cost_usd": self._total_cost,
                "budget_remaining": self.config.budget_limit_usd - self._total_cost
            },
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "recommended_ideas": all_recommended_ideas,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
        return summary
