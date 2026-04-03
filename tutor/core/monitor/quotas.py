"""Quota Manager - 配额管理和警告

监控系统资源使用率，在超过阈值时触发警告。
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable
from enum import Enum

from .collector import SystemMetrics

logger = logging.getLogger(__name__)


class QuotaType(Enum):
    """配额类型"""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    GPU = "gpu"
    GPU_MEMORY = "gpu_memory"


@dataclass
class QuotaWarning:
    """配额警告"""
    quota_type: QuotaType
    current_value: float
    threshold: float
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "quota_type": self.quota_type.value,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "message": self.message,
        }


class QuotaManager:
    """配额管理器

    监控系统资源使用率，在超过阈值时触发警告。
    """

    def __init__(
        self,
        cpu_threshold: float = 90.0,
        memory_threshold: float = 80.0,
        disk_threshold: float = 80.0,
        gpu_threshold: Optional[float] = 80.0,
        gpu_memory_threshold: Optional[float] = 80.0,
        on_warning: Optional[Callable[[QuotaWarning], None]] = None,
    ):
        """初始化配额管理器

        Args:
            cpu_threshold: CPU 使用率阈值 (%)
            memory_threshold: 内存使用率阈值 (%)
            disk_threshold: 磁盘使用率阈值 (%)
            gpu_threshold: GPU 利用率阈值 (%)
            gpu_memory_threshold: GPU 显存使用率阈值 (%)
            on_warning: 警告回调函数
        """
        self.thresholds = {
            QuotaType.CPU: cpu_threshold,
            QuotaType.MEMORY: memory_threshold,
            QuotaType.DISK: disk_threshold,
        }

        if gpu_threshold is not None:
            self.thresholds[QuotaType.GPU] = gpu_threshold
        if gpu_memory_threshold is not None:
            self.thresholds[QuotaType.GPU_MEMORY] = gpu_memory_threshold

        self.on_warning = on_warning
        self._last_warnings: Dict[QuotaType, float] = {}

    def check(self, metrics: SystemMetrics) -> list[QuotaWarning]:
        """检查资源使用率是否超过阈值

        Args:
            metrics: 系统指标数据

        Returns:
            警告列表
        """
        warnings = []

        # 检查 CPU
        cpu_warning = self._check_quota(
            QuotaType.CPU, metrics.cpu_percent, self.thresholds[QuotaType.CPU]
        )
        if cpu_warning:
            warnings.append(cpu_warning)

        # 检查内存
        memory_warning = self._check_quota(
            QuotaType.MEMORY, metrics.memory_percent, self.thresholds[QuotaType.MEMORY]
        )
        if memory_warning:
            warnings.append(memory_warning)

        # 检查磁盘
        disk_warning = self._check_quota(
            QuotaType.DISK, metrics.disk_percent, self.thresholds[QuotaType.DISK]
        )
        if disk_warning:
            warnings.append(disk_warning)

        # 检查 GPU（如果可用）
        if metrics.gpu_utilization is not None and QuotaType.GPU in self.thresholds:
            gpu_warning = self._check_quota(
                QuotaType.GPU, metrics.gpu_utilization, self.thresholds[QuotaType.GPU]
            )
            if gpu_warning:
                warnings.append(gpu_warning)

        # 检查 GPU 显存（如果可用）
        if (
            metrics.gpu_memory_used_mb is not None
            and metrics.gpu_memory_total_mb is not None
            and QuotaType.GPU_MEMORY in self.thresholds
        ):
            gpu_memory_percent = (
                metrics.gpu_memory_used_mb / metrics.gpu_memory_total_mb
            ) * 100
            gpu_memory_warning = self._check_quota(
                QuotaType.GPU_MEMORY,
                gpu_memory_percent,
                self.thresholds[QuotaType.GPU_MEMORY],
            )
            if gpu_memory_warning:
                warnings.append(gpu_memory_warning)

        # 触发回调
        for warning in warnings:
            self._trigger_warning(warning)

        return warnings

    def _check_quota(
        self, quota_type: QuotaType, current_value: float, threshold: float
    ) -> Optional[QuotaWarning]:
        """检查单个配额

        Args:
            quota_type: 配额类型
            current_value: 当前值
            threshold: 阈值

        Returns:
            警告对象，如果未超过阈值则返回 None
        """
        if current_value >= threshold:
            # 检查是否已经发送过警告（防止重复警告）
            last_warning_value = self._last_warnings.get(quota_type)
            if last_warning_value is not None and current_value <= last_warning_value:
                return None

            self._last_warnings[quota_type] = current_value
            warning = QuotaWarning(
                quota_type=quota_type,
                current_value=current_value,
                threshold=threshold,
                message=f"{quota_type.value} usage ({current_value:.1f}%) exceeds threshold ({threshold:.1f}%)",
            )
            return warning

        # 重置警告状态
        self._last_warnings.pop(quota_type, None)
        return None

    def _trigger_warning(self, warning: QuotaWarning) -> None:
        """触发警告

        Args:
            warning: 警告对象
        """
        logger.warning(warning.message)
        if self.on_warning:
            self.on_warning(warning)
