"""SSH 客户端模块

封装 paramiko，提供 SSH 连接、命令执行、文件传输功能。
"""

import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

from .config import RemoteConfig
from .exceptions import (
    SSHConnectionError,
    AuthenticationError,
    CommandExecutionError,
    FileTransferError,
    TimeoutError as DeployTimeoutError,
)

logger = logging.getLogger(__name__)


class SSHClient:
    """SSH 客户端封装

    使用 paramiko 库实现 SSH 连接和远程操作。
    支持密码认证和密钥认证。

    Example:
        ```python
        config = RemoteConfig(
            host="gpu-server.example.com",
            username="researcher",
            key_file="~/.ssh/id_rsa"
        )
        client = SSHClient(config)
        client.connect()
        result = client.execute("nvidia-smi")
        print(result.output)
        client.disconnect()
        ```
    """

    def __init__(self, config: RemoteConfig):
        """初始化 SSH 客户端

        Args:
            config: 远程服务器配置
        """
        self.config = config
        self._client = None
        self._sftp = None
        self._connected = False

    def connect(self) -> None:
        """建立 SSH 连接

        Raises:
            SSHConnectionError: 连接失败
            AuthenticationError: 认证失败
        """
        try:
            import paramiko

            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
                "timeout": self.config.timeout,
            }

            if self.config.key_file:
                # 密钥认证
                key_path = Path(self.config.key_file).expanduser()
                connect_kwargs["key_filename"] = str(key_path)
            else:
                # 密码认证
                connect_kwargs["password"] = self.config.password

            logger.info(
                f"Connecting to {self.config.username}@{self.config.host}:{self.config.port} "
                f"using {self.config.auth_method} auth..."
            )

            self._client.connect(**connect_kwargs)
            self._connected = True

            # 初始化 SFTP
            self._sftp = self._client.open_sftp()

            logger.info(f"Successfully connected to {self.config.host}")

        except ImportError:
            raise SSHConnectionError(
                self.config.host,
                self.config.port,
                self.config.username,
                "paramiko not installed. Install with: pip install paramiko"
            )
        except Exception as e:
            error_msg = str(e)
            if "Authentication failed" in error_msg:
                raise AuthenticationError(
                    self.config.host,
                    self.config.username,
                    self.config.auth_method
                )
            else:
                raise SSHConnectionError(
                    self.config.host,
                    self.config.port,
                    self.config.username,
                    error_msg
                )

    def disconnect(self) -> None:
        """关闭 SSH 连接"""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None

        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        self._connected = False
        logger.info(f"Disconnected from {self.config.host}")

    def is_connected(self) -> bool:
        """检查是否已连接"""
        if not self._client or not self._connected:
            return False
        try:
            transport = self._client.get_transport()
            return transport is not None and transport.is_active()
        except Exception:
            return False

    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        retry_count: Optional[int] = None,
    ) -> "CommandResult":
        """执行远程命令

        Args:
            command: 要执行的命令
            timeout: 超时时间 (秒)，None 表示使用默认配置
            retry_count: 重试次数，None 表示使用默认配置

        Returns:
            CommandResult 对象，包含输出和状态信息

        Raises:
            CommandExecutionError: 命令执行失败
            DeployTimeoutError: 命令执行超时
        """
        if not self.is_connected():
            raise SSHConnectionError(
                self.config.host,
                self.config.port,
                self.config.username,
                "Not connected. Call connect() first."
            )

        timeout = timeout or self.config.timeout
        retry_count = retry_count or self.config.retry_count

        last_error = None
        for attempt in range(retry_count + 1):
            try:
                logger.debug(f"Executing command (attempt {attempt + 1}): {command[:80]}...")

                stdin, stdout, stderr = self._client.exec_command(
                    command,
                    timeout=timeout
                )

                # 等待命令完成
                exit_code = stdout.channel.recv_exit_status()
                output = stdout.read().decode("utf-8", errors="replace")
                error = stderr.read().decode("utf-8", errors="replace")

                result = CommandResult(
                    command=command,
                    exit_code=exit_code,
                    output=output,
                    error=error,
                    host=self.config.host,
                )

                if exit_code != 0:
                    logger.warning(
                        f"Command exited with code {exit_code}: {command[:50]}..."
                    )
                    if attempt < retry_count:
                        logger.info(f"Retrying in 2 seconds...")
                        time.sleep(2)
                        continue

                    raise CommandExecutionError(
                        command,
                        self.config.host,
                        exit_code,
                        error
                    )

                logger.debug(f"Command completed successfully")
                return result

            except Exception as e:
                last_error = e
                if attempt < retry_count:
                    logger.warning(f"Command failed: {e}. Retrying...")
                    time.sleep(2)
                    continue
                raise

        raise last_error

    def execute_streaming(
        self,
        command: str,
        callback,
        timeout: Optional[int] = None,
    ) -> "CommandResult":
        """流式执行远程命令，实时返回输出

        适用于长时间运行的命令，如训练脚本。

        Args:
            command: 要执行的命令
            callback: 回调函数，每收到一行输出调用一次
                     callback(line: str) -> None
            timeout: 超时时间 (秒)

        Returns:
            CommandResult 对象
        """
        if not self.is_connected():
            raise SSHConnectionError(
                self.config.host,
                self.config.port,
                self.config.username,
                "Not connected. Call connect() first."
            )

        timeout = timeout or self.config.timeout

        logger.info(f"Starting streaming command: {command[:80]}...")

        transport = self._client.get_transport()
        channel = transport.open_session()
        channel.exec_command(command)

        output_lines = []
        error_lines = []

        # 设置超时
        channel.settimeout(timeout)

        while not channel.exit_status_ready():
            if channel.recv_ready():
                line = channel.recv(4096).decode("utf-8", errors="replace")
                output_lines.append(line)
                callback(line)
            if channel.recv_stderr_ready():
                line = channel.recv_stderr(4096).decode("utf-8", errors="replace")
                error_lines.append(line)

            time.sleep(0.1)

        # 获取剩余输出
        while channel.recv_ready():
            line = channel.recv(4096).decode("utf-8", errors="replace")
            output_lines.append(line)
            callback(line)

        exit_code = channel.recv_exit_status()
        channel.close()

        return CommandResult(
            command=command,
            exit_code=exit_code,
            output="".join(output_lines),
            error="".join(error_lines),
            host=self.config.host,
        )

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        progress_callback: Optional[callable] = None,
    ) -> None:
        """上传文件到远程服务器

        Args:
            local_path: 本地文件路径
            remote_path: 远程目标路径
            progress_callback: 进度回调函数 (uploaded: int, total: int) -> None

        Raises:
            FileTransferError: 文件传输失败
        """
        if not self.is_connected():
            raise SSHConnectionError(
                self.config.host,
                self.config.port,
                self.config.username,
                "Not connected."
            )

        local_file = Path(local_path)
        if not local_file.exists():
            raise FileTransferError("upload", str(local_path), remote_path, "Local file not found")

        try:
            logger.info(f"Uploading {local_path} to {remote_path}")

            # 获取文件大小
            file_size = local_file.stat().st_size

            def progress_wrapper(uploaded, total):
                if progress_callback:
                    progress_callback(uploaded, total)

            self._sftp.put(
                str(local_file),
                remote_path,
                callback=progress_wrapper,
            )

            logger.info(f"Upload complete: {local_path} -> {remote_path}")

        except Exception as e:
            raise FileTransferError("upload", str(local_path), remote_path, str(e))

    def upload_directory(
        self,
        local_dir: str,
        remote_dir: str,
        exclude_patterns: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None,
    ) -> None:
        """上传整个目录到远程服务器

        Args:
            local_dir: 本地目录路径
            remote_dir: 远程目标目录
            exclude_patterns: 排除的文件模式列表
            progress_callback: 进度回调函数
        """
        if not self.is_connected():
            raise SSHConnectionError(
                self.config.host,
                self.config.port,
                self.config.username,
                "Not connected."
            )

        import fnmatch

        local_path = Path(local_dir)
        if not local_path.is_dir():
            raise FileTransferError("upload", str(local_dir), remote_dir, "Local path is not a directory")

        # 创建远程目录
        self.execute(f"mkdir -p {remote_dir}")

        exclude_patterns = exclude_patterns or []

        # 遍历本地文件
        files_to_upload = []
        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(local_path)
                remote_file = f"{remote_dir}/{rel_path}"

                # 检查是否需要排除
                should_exclude = False
                for pattern in exclude_patterns:
                    if fnmatch.fnmatch(str(rel_path), pattern) or fnmatch.fnmatch(file_path.name, pattern):
                        should_exclude = True
                        break

                if not should_exclude:
                    files_to_upload.append((file_path, remote_file))

        # 上传文件
        total = len(files_to_upload)
        for i, (local_file, remote_file) in enumerate(files_to_upload):
            remote_subdir = str(Path(remote_file).parent)
            self.execute(f"mkdir -p {remote_subdir}")
            self.upload_file(str(local_file), remote_file)
            if progress_callback:
                progress_callback(i + 1, total)

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        progress_callback: Optional[callable] = None,
    ) -> None:
        """从远程服务器下载文件

        Args:
            remote_path: 远程文件路径
            local_path: 本地目标路径
            progress_callback: 进度回调函数

        Raises:
            FileTransferError: 文件传输失败
        """
        if not self.is_connected():
            raise SSHConnectionError(
                self.config.host,
                self.config.port,
                self.config.username,
                "Not connected."
            )

        local_file = Path(local_path)
        local_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"Downloading {remote_path} to {local_path}")

            def progress_wrapper(uploaded, total):
                if progress_callback:
                    progress_callback(uploaded, total)

            self._sftp.get(
                remote_path,
                str(local_file),
                callback=progress_wrapper,
            )

            logger.info(f"Download complete: {remote_path} -> {local_path}")

        except Exception as e:
            raise FileTransferError("download", str(local_path), remote_path, str(e))

    def download_directory(
        self,
        remote_dir: str,
        local_dir: str,
        progress_callback: Optional[callable] = None,
    ) -> None:
        """从远程服务器下载整个目录

        Args:
            remote_dir: 远程目录路径
            local_dir: 本地目标目录
            progress_callback: 进度回调函数
        """
        if not self.is_connected():
            raise SSHConnectionError(
                self.config.host,
                self.config.port,
                self.config.username,
                "Not connected."
            )

        local_path = Path(local_dir)
        local_path.mkdir(parents=True, exist_ok=True)

        # 获取远程目录中的文件列表
        result = self.execute(f"find {remote_dir} -type f 2>/dev/null")
        remote_files = [f.strip() for f in result.output.split("\n") if f.strip()]

        total = len(remote_files)
        for i, remote_file in enumerate(remote_files):
            rel_path = Path(remote_file).relative_to(Path(remote_dir))
            local_file = local_path / rel_path
            local_file.parent.mkdir(parents=True, exist_ok=True)

            self.download_file(remote_file, str(local_file))
            if progress_callback:
                progress_callback(i + 1, total)

    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()
        return False


@dataclass
class CommandResult:
    """命令执行结果

    Attributes:
        command: 执行的命令
        exit_code: 退出码
        output: 标准输出
        error: 标准错误输出
        host: 执行命令的主机
    """

    command: str
    exit_code: int
    output: str
    error: str
    host: str

    @property
    def success(self) -> bool:
        """命令是否成功执行"""
        return self.exit_code == 0

    def __str__(self) -> str:
        return (
            f"CommandResult(exit_code={self.exit_code}, "
            f"host={self.host}, output_len={len(self.output)})"
        )
