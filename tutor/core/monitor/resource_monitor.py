"""TUTOR Resource Monitor - 系统资源采集与监控

定期采集 CPU、内存、磁盘和 GPU 使用情况。
"""

import logging
import subprocess
import threading
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

logger = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class ResourceSnapshot:
    """系统资源快照"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_free_gb: float
    gpu_utilization: Optional[float] = None
    gpu_memory_used_gb: Optional[float] = None
    gpu_memory_total_gb: Optional[float] = None


class ResourceMonitor:
    """系统资源监控器"""

    def __init__(self, interval_seconds: int = 60, gpu_enabled: bool = True) -> None:
        self.interval_seconds = interval_seconds
        self.gpu_enabled = gpu_enabled
        self._history: List[ResourceSnapshot] = []
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def collect(self) -> ResourceSnapshot:
        """单次采集资源快照"""
        timestamp = datetime.now(timezone.utc)

        if HAS_PSUTIL:
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            memory_percent = mem.percent
            memory_used_gb = round(mem.used / (1024**3), 2)
            memory_total_gb = round(mem.total / (1024**3), 2)
        else:
            cpu = 0.0
            memory_percent = 0.0
            memory_used_gb = 0.0
            memory_total_gb = 0.0

        disk = shutil.disk_usage("/")
        disk_total_gb = round(disk.total / (1024**3), 2)
        disk_free_gb = round(disk.free / (1024**3), 2)
        disk_percent = round((1 - disk.free / disk.total) * 100, 2) if disk.total > 0 else 0.0

        gpu_util = gpu_mem_used = gpu_mem_total = None
        if self.gpu_enabled:
            gpu_util, gpu_mem_used, gpu_mem_total = self._collect_gpu()

        snapshot = ResourceSnapshot(
            timestamp=timestamp,
            cpu_percent=cpu,
            memory_percent=memory_percent,
            memory_used_gb=memory_used_gb,
            memory_total_gb=memory_total_gb,
            disk_percent=disk_percent,
            disk_free_gb=disk_free_gb,
            gpu_utilization=gpu_util,
            gpu_memory_used_gb=gpu_mem_used,
            gpu_memory_total_gb=gpu_mem_total,
        )
        return snapshot

    @staticmethod
    def _collect_gpu() -> tuple:
        """采集 GPU 信息，失败返回 None"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None, None, None
            parts = result.stdout.strip().split(", ")
            return (
                float(parts[0]),
                round(float(parts[1]) / 1024, 2),
                round(float(parts[2]) / 1024, 2),
            )
        except Exception:
            return None, None, None

    
    def is_running(self) -> bool:
        return self._running

    def set_warning_callback(self, callback) -> None:
        # 兼容 QuotaManager 逻辑
        pass

    def start(self) -> None:
        """后台线程定期采集"""
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
        logger.info(f"ResourceMonitor started (interval={self.interval_seconds}s)")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds * 2)
        logger.info("ResourceMonitor stopped")

    def _collect_loop(self) -> None:
        while self._running:
            snapshot = self.collect()
            with self._lock:
                self._history.append(snapshot)
            # Use shared stop event so stop() can wake this thread immediately
            self._stop_event.wait(self.interval_seconds)

    def get_history(self) -> List[ResourceSnapshot]:
        with self._lock:
            return list(self._history)

    def get_latest(self) -> Optional[ResourceSnapshot]:
        with self._lock:
            return self._history[-1] if self._history else None
