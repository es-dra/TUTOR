"""远程执行器模块

管理远程工作空间，执行实验，收集结果。
"""

import logging
import uuid
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Callable, Dict, Any

from .config import RemoteConfig, DeploymentProfile
from .ssh_client import SSHClient
from .exceptions import (
    RemoteEnvironmentError,
    ExperimentExecutionError,
    WorkspaceError,
    TimeoutError as DeployTimeoutError,
)

logger = logging.getLogger(__name__)


class RemoteExecutor:
    """远程实验执行器

    管理远程 GPU 服务器上的实验执行全流程。

    Example:
        ```python
        executor = RemoteExecutor(config)
        executor.connect()

        # 部署代码
        workspace = executor.create_workspace("experiment_001")
        executor.deploy_code("/local/code", workspace)

        # 执行实验
        result = executor.run_experiment(
            workspace,
            "python train.py --epochs 100",
            timeout_minutes=60,
        )

        # 拉回结果
        executor.fetch_results(workspace, "/local/results")

        executor.cleanup()
        executor.disconnect()
        ```
    """

    def __init__(self, config: RemoteConfig, profile: Optional[DeploymentProfile] = None):
        """初始化远程执行器

        Args:
            config: 远程服务器配置
            profile: 部署配置文件
        """
        self.config = config
        self.profile = profile
        self.ssh = SSHClient(config)
        self._workspace_id = None
        self._connected = False

    def connect(self) -> None:
        """建立 SSH 连接"""
        self.ssh.connect()
        self._connected = True

    def disconnect(self) -> None:
        """关闭 SSH 连接"""
        self.ssh.disconnect()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self.ssh.is_connected()

    # ==================== 环境检查 ====================

    def check_environment(self) -> Dict[str, Any]:
        """检查远程环境

        Returns:
            环境信息字典

        Raises:
            RemoteEnvironmentError: 环境检查失败
        """
        if not self.is_connected:
            raise RemoteEnvironmentError("connection", "connected", "not connected")

        checks = {}

        # 检查 Python
        result = self.ssh.execute(f"{self.config.get_python_command()} --version")
        if result.success:
            checks["python_version"] = result.output.strip()
        else:
            raise RemoteEnvironmentError("python", "available", "not found")

        # 检查 GPU
        if self.config.gpu_required:
            result = self.ssh.execute("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
            if result.success:
                checks["gpu_available"] = True
                checks["gpu_info"] = result.output.strip()
            else:
                if self.config.gpu_required:
                    raise RemoteEnvironmentError("gpu", "available", "not found")
                checks["gpu_available"] = False

        # 检查磁盘空间
        result = self.ssh.execute(
            f"df -BG {self.config.remote_workspace} | tail -1 | awk '{{print $4}}' | tr -d 'G'"
        )
        if result.success:
            try:
                free_gb = int(result.output.strip())
                checks["disk_space_gb"] = free_gb
                if free_gb < 10:
                    logger.warning(f"Low disk space: {free_gb}GB remaining")
            except ValueError:
                pass

        # 检查 Conda 环境 (如果指定)
        if self.config.conda_env:
            result = self.ssh.execute(f"conda env list | grep {self.config.conda_env}")
            if result.success:
                checks["conda_env"] = self.config.conda_env
            else:
                raise RemoteEnvironmentError("conda_env", self.config.conda_env, "not found")

        logger.info(f"Environment check passed: {checks}")
        return checks

    # ==================== 工作空间管理 ====================

    def create_workspace(self, experiment_id: Optional[str] = None) -> str:
        """创建远程工作空间

        Args:
            experiment_id: 实验 ID，用于命名工作空间

        Returns:
            工作空间路径
        """
        workspace_id = experiment_id or str(uuid.uuid4())[:8]
        self._workspace_id = workspace_id

        workspace_path = f"{self.config.remote_workspace}/{workspace_id}"

        # 创建工作空间目录
        result = self.ssh.execute(f"mkdir -p {workspace_path}")

        if not result.success:
            raise WorkspaceError(
                workspace_path,
                "create",
                f"Failed to create workspace: {result.error}"
            )

        logger.info(f"Created workspace: {workspace_path}")
        return workspace_path

    def cleanup_workspace(self, workspace_path: Optional[str] = None) -> None:
        """清理远程工作空间

        Args:
            workspace_path: 工作空间路径，None 则清理当前工作空间
        """
        workspace = workspace_path or f"{self.config.remote_workspace}/{self._workspace_id}"

        logger.info(f"Cleaning up workspace: {workspace}")
        result = self.ssh.execute(f"rm -rf {workspace}")

        if not result.success:
            logger.warning(f"Failed to cleanup workspace: {result.error}")

    # ==================== 代码部署 ====================

    def deploy_code(
        self,
        local_code_path: str,
        remote_workspace: str,
        exclude_patterns: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """部署代码到远程服务器

        Args:
            local_code_path: 本地代码路径
            remote_workspace: 远程工作空间路径
            exclude_patterns: 排除的文件模式
            progress_callback: 进度回调函数
        """
        local_path = Path(local_code_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Local code path not found: {local_code_path}")

        exclude_patterns = exclude_patterns or self.profile.exclude_patterns if self.profile else []

        # 如果是目录，使用 tar 打包上传
        if local_path.is_dir():
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tar_file:
                tar_path = tar_file.name

            logger.info(f"Packing code to {tar_path}")
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(local_path, arcname=local_path.name)

            remote_tar = f"{remote_workspace}/code.tar.gz"
            self.ssh.upload_file(tar_path, remote_tar, progress_callback)

            # 解压
            extract_cmd = f"cd {remote_workspace} && tar -xzf code.tar.gz && rm code.tar.gz"
            result = self.ssh.execute(extract_cmd)

            if not result.success:
                raise WorkspaceError(
                    remote_workspace,
                    "extract",
                    f"Failed to extract code: {result.error}"
                )

            # 清理本地 tar 文件
            Path(tar_path).unlink()

            logger.info(f"Code deployed to {remote_workspace}")

        else:
            # 单文件上传
            remote_file = f"{remote_workspace}/{local_path.name}"
            self.ssh.upload_file(str(local_path), remote_file, progress_callback)
            logger.info(f"File deployed to {remote_file}")

    def install_dependencies(
        self,
        workspace_path: str,
        requirements_file: str = "requirements.txt",
        timeout_minutes: int = 10,
    ) -> Dict[str, Any]:
        """在远程服务器安装依赖

        Args:
            workspace_path: 工作空间路径
            requirements_file: requirements.txt 文件名
            timeout_minutes: 超时时间 (分钟)

        Returns:
            安装结果信息
        """
        req_file = f"{workspace_path}/{requirements_file}"

        # 检查 requirements.txt 是否存在
        check_result = self.ssh.execute(f"test -f {req_file} && echo exists")
        if not check_result.success:
            logger.info("No requirements.txt found, skipping dependency installation")
            return {"installed": False, "reason": "No requirements.txt"}

        # 构建 pip 安装命令
        pip_cmd = self.config.get_python_command()

        extra_index = ""
        if self.profile and self.profile.pip_extra_index:
            extra_index = f" -i {self.profile.pip_extra_index}"

        install_cmd = (
            f"cd {workspace_path} && "
            f"{pip_cmd} -m pip install -r {requirements_file}{extra_index} "
            f"--quiet 2>&1"
        )

        logger.info(f"Installing dependencies (timeout: {timeout_minutes}min)...")

        try:
            result = self.ssh.execute(install_cmd, timeout=timeout_minutes * 60)

            if result.success:
                logger.info("Dependencies installed successfully")
                return {
                    "installed": True,
                    "output": result.output,
                }
            else:
                logger.warning(f"Dependency installation had issues: {result.error}")
                return {
                    "installed": True,
                    "warning": result.error,
                }

        except Exception as e:
            logger.warning(f"Dependency installation failed: {e}")
            return {
                "installed": False,
                "error": str(e),
            }

    # ==================== 实验执行 ====================

    def run_experiment(
        self,
        workspace_path: str,
        experiment_command: str,
        log_callback: Optional[Callable[[str], None]] = None,
        timeout_minutes: Optional[int] = None,
    ) -> "ExperimentResult":
        """在远程服务器运行实验

        Args:
            workspace_path: 工作空间路径
            experiment_command: 实验命令
            log_callback: 日志回调函数
            timeout_minutes: 超时时间 (分钟)，None 使用配置默认值

        Returns:
            实验结果

        Raises:
            ExperimentExecutionError: 实验执行失败
        """
        timeout = timeout_minutes or self.config.experiment_timeout_minutes
        timeout_seconds = timeout * 60

        # 构建完整命令 (设置环境变量)
        gpu_env = ""
        if self.config.gpu_required:
            gpu_env = f"export CUDA_VISIBLE_DEVICES={self.config.gpu_device} && "

        full_command = (
            f"cd {workspace_path} && "
            f"{gpu_env}"
            f"{self.config.get_python_command()} -u -c '{experiment_command}' "
            f"2>&1"
        )

        logger.info(f"Starting experiment (timeout: {timeout}min)...")
        logger.debug(f"Command: {experiment_command[:100]}...")

        try:
            if log_callback:
                result = self.ssh.execute_streaming(
                    full_command,
                    callback=log_callback,
                    timeout=timeout_seconds,
                )
            else:
                result = self.ssh.execute(full_command, timeout=timeout_seconds)

            # 解析输出中的指标
            metrics = self._extract_metrics(result.output)

            experiment_result = ExperimentResult(
                experiment_id=self._workspace_id or "unknown",
                workspace_path=workspace_path,
                success=result.success,
                exit_code=result.exit_code,
                output=result.output,
                error=result.error,
                metrics=metrics,
            )

            if not result.success:
                raise ExperimentExecutionError(
                    self._workspace_id or "unknown",
                    "execution",
                    f"Exit code: {result.exit_code}\n{result.error[:500]}",
                    self.config.host
                )

            logger.info(f"Experiment completed successfully")
            return experiment_result

        except Exception as e:
            if isinstance(e, ExperimentExecutionError):
                raise
            raise ExperimentExecutionError(
                self._workspace_id or "unknown",
                "execution",
                str(e),
                self.config.host
            )

    def _extract_metrics(self, output: str) -> Dict[str, float]:
        """从实验输出中提取指标

        支持格式:
        - "accuracy: 0.95"
        - "loss = 0.123"
        - "val_loss: 1.234"
        """
        import re
        metrics = {}

        patterns = [
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*[:=]\s*([\d.]+(?:[eE][+-]?\d+)?)',
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\|\s*([\d.]+(?:[eE][+-]?\d+)?)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output)
            for key, value in matches:
                key = key.lower().strip()
                try:
                    metrics[key] = float(value)
                except ValueError:
                    pass

        return metrics

    # ==================== 结果收集 ====================

    def fetch_results(
        self,
        workspace_path: str,
        local_results_dir: str,
        artifacts_pattern: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        """拉取实验结果到本地

        Args:
            workspace_path: 远程工作空间路径
            local_results_dir: 本地结果目录
            artifacts_pattern: 要拉取的文件模式列表
            progress_callback: 进度回调函数

        Returns:
            拉取的文件路径列表
        """
        import fnmatch

        local_dir = Path(local_results_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        # 默认拉取常见的实验结果文件
        artifacts_pattern = artifacts_pattern or [
            "*.png", "*.jpg", "*.pdf", "*.csv", "*.json",
            "*.txt", "*.log",
            "outputs/**/*", "results/**/*", "figures/**/*",
        ]

        # 获取工作空间中的文件列表
        result = self.ssh.execute(f"find {workspace_path} -type f 2>/dev/null")
        all_files = [f.strip() for f in result.output.split("\n") if f.strip()]

        # 筛选要拉取的文件
        files_to_fetch = []
        for file_path in all_files:
            rel_path = Path(file_path).relative_to(Path(workspace_path))
            for pattern in artifacts_pattern:
                if fnmatch.fnmatch(str(rel_path), pattern) or fnmatch.fnmatch(file_path, pattern):
                    files_to_fetch.append(file_path)
                    break

        if not files_to_fetch:
            logger.info("No artifacts found to fetch")
            return []

        # 拉取文件
        fetched_files = []
        total = len(files_to_fetch)

        for i, remote_file in enumerate(files_to_fetch):
            rel_path = Path(remote_file).relative_to(Path(workspace_path))
            local_file = local_dir / rel_path
            local_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                self.ssh.download_file(remote_file, str(local_file))
                fetched_files.append(str(local_file))
            except Exception as e:
                logger.warning(f"Failed to download {remote_file}: {e}")

            if progress_callback:
                progress_callback(i + 1, total)

        logger.info(f"Fetched {len(fetched_files)} result files to {local_dir}")
        return fetched_files

    def fetch_experiment_logs(self, workspace_path: str) -> str:
        """获取实验日志

        Args:
            workspace_path: 工作空间路径

        Returns:
            实验日志内容
        """
        # 查找日志文件
        result = self.ssh.execute(
            f"find {workspace_path} -name '*.log' -type f 2>/dev/null | head -5"
        )

        log_files = [f.strip() for f in result.output.split("\n") if f.strip()]

        if not log_files:
            return ""

        # 读取最新的日志文件
        latest_log = log_files[0]
        result = self.ssh.execute(f"cat {latest_log}")

        return result.output

    # ==================== 便捷方法 ====================

    def execute_full_pipeline(
        self,
        local_code_path: str,
        experiment_command: str,
        experiment_id: str,
        local_results_dir: str,
        timeout_minutes: int = 60,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> "ExperimentResult":
        """执行完整的远程实验流程

        包含: 环境检查 -> 创建工作空间 -> 部署代码 -> 安装依赖 -> 执行实验 -> 拉取结果

        Args:
            local_code_path: 本地代码路径
            experiment_command: 实验命令
            experiment_id: 实验 ID
            local_results_dir: 本地结果目录
            timeout_minutes: 实验超时时间
            log_callback: 日志回调函数

        Returns:
            实验结果
        """
        # 检查环境
        self.check_environment()

        # 创建工作空间
        workspace = self.create_workspace(experiment_id)

        try:
            # 部署代码
            self.deploy_code(local_code_path, workspace)

            # 安装依赖
            self.install_dependencies(workspace)

            # 执行实验
            result = self.run_experiment(
                workspace,
                experiment_command,
                log_callback=log_callback,
                timeout_minutes=timeout_minutes,
            )

            # 拉取结果
            self.fetch_results(workspace, local_results_dir)

            return result

        finally:
            # 清理远程工作空间
            self.cleanup_workspace(workspace)

    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()
        return False


@dataclass
class ExperimentResult:
    """实验结果

    Attributes:
        experiment_id: 实验 ID
        workspace_path: 远程工作空间路径
        success: 是否成功
        exit_code: 退出码
        output: 实验输出
        error: 错误信息
        metrics: 提取的指标
    """

    experiment_id: str
    workspace_path: str
    success: bool
    exit_code: int
    output: str
    error: str
    metrics: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "workspace_path": self.workspace_path,
            "success": self.success,
            "exit_code": self.exit_code,
            "output": self.output[:1000] if self.output else "",
            "error": self.error[:500] if self.error else "",
            "metrics": self.metrics,
        }
