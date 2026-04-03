"""部署异常模块

定义远程部署相关的异常类型。
"""


class DeploymentError(Exception):
    """部署基础异常"""

    def __init__(self, message: str, host: str = None, details: str = None):
        self.host = host
        self.details = details
        super().__init__(message)

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.host:
            parts.append(f"Host: {self.host}")
        if self.details:
            parts.append(f"Details: {self.details}")
        return " | ".join(parts)


class SSHConnectionError(DeploymentError):
    """SSH 连接失败"""

    def __init__(self, host: str, port: int, username: str, reason: str):
        super().__init__(
            f"Failed to connect to {username}@{host}:{port}",
            host=host,
            details=reason
        )
        self.port = port
        self.username = username
        self.reason = reason


class AuthenticationError(DeploymentError):
    """SSH 认证失败"""

    def __init__(self, host: str, username: str, method: str):
        super().__init__(
            f"Authentication failed for {username}@{host} using {method}",
            host=host,
            details=f"Method: {method}"
        )
        self.username = username
        self.method = method


class CommandExecutionError(DeploymentError):
    """远程命令执行失败"""

    def __init__(self, command: str, host: str, exit_code: int, stderr: str = ""):
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(
            f"Command failed with exit code {exit_code}",
            host=host,
            details=f"Command: {command[:100]}...\nStderr: {stderr[:200]}"
        )


class FileTransferError(DeploymentError):
    """文件传输失败"""

    def __init__(self, operation: str, local_path: str, remote_path: str, reason: str):
        self.operation = operation  # "upload" or "download"
        self.local_path = local_path
        self.remote_path = remote_path
        super().__init__(
            f"Failed to {operation} file",
            details=f"Local: {local_path}\nRemote: {remote_path}\nReason: {reason}"
        )


class TimeoutError(DeploymentError):
    """操作超时"""

    def __init__(self, operation: str, timeout_seconds: int, host: str = None):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"{operation} timed out after {timeout_seconds}s",
            host=host
        )


class RemoteEnvironmentError(DeploymentError):
    """远程环境检查失败"""

    def __init__(self, check_name: str, expected: str, actual: str, host: str = None):
        self.check_name = check_name
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Environment check '{check_name}' failed",
            host=host,
            details=f"Expected: {expected}, Actual: {actual}"
        )


class ExperimentExecutionError(DeploymentError):
    """实验执行失败"""

    def __init__(self, experiment_id: str, stage: str, message: str, host: str = None):
        self.experiment_id = experiment_id
        self.stage = stage
        super().__init__(
            f"Experiment {experiment_id} failed at stage: {stage}",
            host=host,
            details=message
        )


class WorkspaceError(DeploymentError):
    """远程工作空间错误"""

    def __init__(self, workspace: str, operation: str, reason: str, host: str = None):
        self.workspace = workspace
        self.operation = operation
        super().__init__(
            f"Workspace operation '{operation}' failed",
            host=host,
            details=f"Workspace: {workspace}\nReason: {reason}"
        )


# 别名 (用于兼容不同导入场景)
DeployTimeoutError = TimeoutError
