"""TUTOR Deployment Module - 远程实验部署模块

提供远程 GPU 服务器上的实验执行能力。

核心组件:
- RemoteConfig: 远程服务器配置
- SSHClient: SSH 客户端封装
- RemoteExecutor: 远程实验执行器
"""

from .config import (
    RemoteConfig,
    DeploymentProfile,
    load_deployment_profile,
    save_deployment_profile,
)
from .ssh_client import SSHClient, CommandResult
from .remote_executor import RemoteExecutor, ExperimentResult
from .exceptions import (
    DeploymentError,
    SSHConnectionError,
    AuthenticationError,
    CommandExecutionError,
    FileTransferError,
    DeployTimeoutError,
    RemoteEnvironmentError,
    ExperimentExecutionError,
    WorkspaceError,
)

__all__ = [
    # Config
    "RemoteConfig",
    "DeploymentProfile",
    "load_deployment_profile",
    "save_deployment_profile",
    # SSH Client
    "SSHClient",
    "CommandResult",
    # Executor
    "RemoteExecutor",
    "ExperimentResult",
    # Exceptions
    "DeploymentError",
    "SSHConnectionError",
    "AuthenticationError",
    "CommandExecutionError",
    "FileTransferError",
    "DeployTimeoutError",
    "RemoteEnvironmentError",
    "ExperimentExecutionError",
    "WorkspaceError",
]
