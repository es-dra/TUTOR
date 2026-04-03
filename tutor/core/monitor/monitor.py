"""Resource Monitor - 资源监控主模块

整合资源采集和配额管理，提供定时监控功能。
"""

import logging
import threading
import time
from typing import Optional, Callable
from dataclasses import dataclass

from .collector import ResourceCollector, SystemMetrics
from .quotas import QuotaManager, QuotaWarning, QuotaType

logger = logging.getLogger(__name__)


@dataclass
class MonitorConfig:
    """监控配置"""
    interval_seconds: float = 60.0  # 监控间隔（秒）
    cpu_threshold: float = 90.0
    memory_threshold: float = 80.0
    disk_threshold: float = 80.0
    gpu_threshold: Optional[float] = 80.0
    gpu_memory_threshold: Optional[float] = 80.0
    enable_gpu: bool = True


class ResourceMonitor:
    """资源监控器

    定时采集系统资源数据，检查是否超过配额阈值。
    """

    def __init__(self, config: MonitorConfig):
        """初始化监控器

        Args:
            config: 监控配置
        """
        self.config = config
        self.collector = ResourceCollector(enable_gpu=config.enable_gpu)
        self.quota_manager = QuotaManager(
            cpu_threshold=config.cpu_threshold,
            memory_threshold=config.memory_threshold,
            disk_threshold=config.disk_threshold,
            gpu_threshold=config.gpu_threshold,
            gpu_memory_threshold=config.gpu_memory_threshold,
            on_warning=self._on_quota_warning,
        )
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._on_warning_callback: Optional[Callable[[QuotaWarning], None]] = None

    def start(self) -> None:
        """启动监控"""
        if self._running:
            logger.warning("Resource monitor already running")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Resource monitor started")

    def stop(self) -> None:
        """停止监控"""
        if not self._running:
            logger.warning("Resource monitor not running")
            return

        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Resource monitor stopped")

    def collect_once(self) -> SystemMetrics:
        """采集一次资源数据

        Returns:
            SystemMetrics: 系统指标数据
        """
        return self.collector.collect()

    def check_quota(self, metrics: SystemMetrics) -> list[QuotaWarning]:
        """检查配额

        Args:
            metrics: 系统指标数据

        Returns:
            警告列表
        """
        return self.quota_manager.check(metrics)

    def set_warning_callback(self, callback: Callable[[QuotaWarning], None]) -> None:
        """设置警告回调函数

        Args:
            callback: 警告回调函数
        """
        self._on_warning_callback = callback

    def _monitor_loop(self) -> None:
        """监控循环"""
        while not self._stop_event.is_set():
            try:
                metrics = self.collector.collect()
                warnings = self.quota_manager.check(metrics)
                logger.debug(f"Collected metrics: {metrics.to_dict()}")
            except Exception as e:
                logger.error(f"Failed to collect metrics: {e}")

            # 等待下一个监控间隔
            self._stop_event.wait(self.config.interval_seconds)

    def _on_quota_warning(self, warning: QuotaWarning) -> None:
        """配额警告回调

        Args:
            warning: 警告对象
        """
        # 调用外部回调
        if self._on_warning_callback:
            self._on_warning_callback(warning)

    def is_running(self) -> bool:
        """检查监控是否在运行

        Returns:
            是否在运行
        """
        return self._running
