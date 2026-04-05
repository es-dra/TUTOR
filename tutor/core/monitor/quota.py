"""TUTOR Quota Manager - 资源配额与预算管理

监控资源使用阈值，在接近或超过限制时生成告警。
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .cost_tracker import CostTracker
from .resource_collector import ResourceSnapshot

logger = logging.getLogger(__name__)


@dataclass
class QuotaConfig:
    """配额配置"""

    budget_limit_usd: float = 100.0
    warn_threshold_percent: float = 80.0
    disk_warn_percent: float = 85.0
    memory_warn_percent: float = 90.0
    gpu_memory_warn_percent: float = 90.0


@dataclass
class QuotaStatus:
    """配额状态"""

    budget_used_usd: float = 0.0
    budget_remaining_usd: float = 100.0
    budget_percent: float = 0.0
    warnings: List[str] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    is_over_quota: bool = False


class QuotaManager:
    """配额管理器"""

    def __init__(self, config: QuotaConfig, cost_tracker: CostTracker) -> None:
        self.config = config
        self.cost_tracker = cost_tracker

    def check(self, snapshot: ResourceSnapshot) -> QuotaStatus:
        """检查资源快照是否触发告警"""
        status = QuotaStatus()
        spent = self.cost_tracker.total()
        status.budget_used_usd = spent
        status.budget_remaining_usd = self.config.budget_limit_usd - spent
        status.budget_percent = (
            round(spent / self.config.budget_limit_usd * 100, 2)
            if self.config.budget_limit_usd > 0
            else 0
        )

        if status.budget_percent >= 100:
            status.is_over_quota = True
            status.alerts.append(
                f"Budget exceeded: {spent:.2f}/{self.config.budget_limit_usd:.2f} USD"
            )
        elif status.budget_percent >= self.config.warn_threshold_percent:
            status.warnings.append(f"Budget at {status.budget_percent:.1f}%")

        if snapshot.disk_percent >= self.config.disk_warn_percent:
            status.warnings.append(
                f"Disk usage {snapshot.disk_percent:.1f}% >= {self.config.disk_warn_percent}%"
            )

        if snapshot.memory_percent >= self.config.memory_warn_percent:
            status.warnings.append(
                f"Memory usage {snapshot.memory_percent:.1f}% >= {self.config.memory_warn_percent}%"
            )

        if (
            snapshot.gpu_memory_total_gb
            and snapshot.gpu_memory_total_gb > 0
            and snapshot.gpu_memory_used_gb is not None
        ):
            gpu_pct = round(
                snapshot.gpu_memory_used_gb / snapshot.gpu_memory_total_gb * 100, 2
            )
            if gpu_pct >= self.config.gpu_memory_warn_percent:
                status.warnings.append(f"GPU memory usage {gpu_pct:.1f}%")

        return status

    def record_cost(
        self,
        amount_usd: float,
        description: str = "",
        model: str = "",
        workflow_id: str = "",
    ) -> None:
        from .cost_tracker import CostEntry
        from datetime import datetime, timezone

        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat() + "Z",
            amount_usd=amount_usd,
            model=model,
            description=description,
            workflow_id=workflow_id,
        )
        self.cost_tracker.record(entry)

    def get_usage(self) -> QuotaStatus:
        """获取当前使用状态（不含资源快照）"""
        status = QuotaStatus()
        spent = self.cost_tracker.total()
        status.budget_used_usd = spent
        status.budget_remaining_usd = self.config.budget_limit_usd - spent
        status.budget_percent = (
            round(spent / self.config.budget_limit_usd * 100, 2)
            if self.config.budget_limit_usd > 0
            else 0
        )
        status.is_over_quota = spent > self.config.budget_limit_usd
        if status.is_over_quota:
            status.alerts.append(
                f"Budget exceeded: {spent:.2f}/{self.config.budget_limit_usd:.2f} USD"
            )
        return status
