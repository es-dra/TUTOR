"""Resource Collector - 系统资源数据采集

采集 CPU、内存、磁盘、GPU 等系统资源数据。
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """系统指标数据"""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    disk_percent: float
    gpu_utilization: Optional[float] = None
    gpu_memory_used_mb: Optional[float] = None
    gpu_memory_total_mb: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "disk_used_gb": self.disk_used_gb,
            "disk_total_gb": self.disk_total_gb,
            "disk_percent": self.disk_percent,
        }
        if self.gpu_utilization is not None:
            data["gpu_utilization"] = self.gpu_utilization
        if self.gpu_memory_used_mb is not None:
            data["gpu_memory_used_mb"] = self.gpu_memory_used_mb
        if self.gpu_memory_total_mb is not None:
            data["gpu_memory_total_mb"] = self.gpu_memory_total_mb
        return data


class ResourceCollector:
    """系统资源采集器"""

    def __init__(self, enable_gpu: bool = True):
        self.enable_gpu = enable_gpu
        self._nvidia_smi_available = False

        if self.enable_gpu:
            self._check_nvidia_smi()

    def _check_nvidia_smi(self) -> None:
        """检查 nvidia-smi 是否可用"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._nvidia_smi_available = result.returncode == 0
            if self._nvidia_smi_available:
                logger.info("NVIDIA GPU monitoring enabled")
            else:
                logger.warning("NVIDIA GPU not available, disabling GPU monitoring")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.debug("nvidia-smi not found, GPU monitoring disabled")
            self._nvidia_smi_available = False

    def collect(self) -> SystemMetrics:
        """采集系统资源指标

        Returns:
            SystemMetrics: 系统指标数据
        """
        cpu_percent, memory_percent, memory_used_mb, memory_total_mb = self._collect_cpu_memory()
        disk_used_gb, disk_total_gb, disk_percent = self._collect_disk()
        gpu_utilization, gpu_memory_used_mb, gpu_memory_total_mb = self._collect_gpu()

        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            disk_percent=disk_percent,
            gpu_utilization=gpu_utilization,
            gpu_memory_used_mb=gpu_memory_used_mb,
            gpu_memory_total_mb=gpu_memory_total_mb,
        )

    def _collect_cpu_memory(self) -> tuple:
        """采集 CPU 和内存数据"""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            memory_total_mb = memory.total / (1024 * 1024)
        except ImportError:
            logger.warning("psutil not available, using fallback metrics")
            cpu_percent = 0.0
            memory_percent = 0.0
            memory_used_mb = 0.0
            memory_total_mb = 0.0
        except Exception as e:
            logger.error(f"Failed to collect CPU/memory metrics: {e}")
            cpu_percent = 0.0
            memory_percent = 0.0
            memory_used_mb = 0.0
            memory_total_mb = 0.0

        return cpu_percent, memory_percent, memory_used_mb, memory_total_mb

    def _collect_disk(self) -> tuple:
        """采集磁盘数据"""
        try:
            import shutil
            usage = shutil.disk_usage("/")
            disk_used_gb = usage.used / (1024**3)
            disk_total_gb = usage.total / (1024**3)
            disk_percent = (usage.used / usage.total) * 100
        except Exception as e:
            logger.error(f"Failed to collect disk metrics: {e}")
            disk_used_gb = 0.0
            disk_total_gb = 0.0
            disk_percent = 0.0

        return disk_used_gb, disk_total_gb, disk_percent

    def _collect_gpu(self) -> tuple:
        """采集 GPU 数据"""
        if not self.enable_gpu or not self._nvidia_smi_available:
            return None, None, None

        try:
            # 查询 GPU 利用率
            util_result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            gpu_utilization = (
                float(util_result.stdout.strip()) if util_result.returncode == 0 else None
            )

            # 查询 GPU 显存
            mem_result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if mem_result.returncode == 0:
                mem_parts = mem_result.stdout.strip().split(", ")
                gpu_memory_used_mb = float(mem_parts[0])
                gpu_memory_total_mb = float(mem_parts[1])
            else:
                gpu_memory_used_mb = None
                gpu_memory_total_mb = None

        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to collect GPU metrics: {e}")
            gpu_utilization = None
            gpu_memory_used_mb = None
            gpu_memory_total_mb = None

        return gpu_utilization, gpu_memory_used_mb, gpu_memory_total_mb
