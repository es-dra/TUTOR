"""部署配置模块

定义远程部署所需的配置类和配置管理。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class RemoteConfig:
    """远程服务器配置

    Attributes:
        host: 服务器主机名或 IP 地址
        port: SSH 端口号，默认 22
        username: SSH 用户名
        password: SSH 密码 (可选，与 key_file 二选一)
        key_file: SSH 私钥文件路径 (可选，与 password 二选一)
        remote_workspace: 远程工作目录，默认为 /tmp/tutor-experiments
        python_path: 远程 Python 解释器路径，默认 python
        conda_env: Conda 环境名称 (可选)
        timeout: SSH 连接超时时间 (秒)，默认 30
        retry_count: 命令执行失败重试次数，默认 2
    """

    host: str
    port: int = 22
    username: str = ""
    password: Optional[str] = None
    key_file: Optional[str] = None
    remote_workspace: str = "/tmp/tutor-experiments"
    python_path: str = "python"
    conda_env: Optional[str] = None
    timeout: int = 30
    retry_count: int = 2

    # GPU 配置
    gpu_required: bool = True
    gpu_device: str = "0"  # GPU 设备号，多卡用逗号分隔

    # 实验配置
    experiment_timeout_minutes: int = 60  # 实验超时时间

    def __post_init__(self):
        """验证配置"""
        if not self.username:
            raise ValueError("username is required")

        if not self.password and not self.key_file:
            raise ValueError("Either password or key_file must be provided")

        if self.key_file:
            key_path = Path(self.key_file).expanduser()
            if not key_path.exists():
                raise ValueError(f"SSH key file not found: {key_path}")

    @property
    def auth_method(self) -> str:
        """返回认证方式"""
        if self.key_file:
            return "key"
        return "password"

    def get_python_command(self) -> str:
        """获取 Python 命令"""
        if self.conda_env:
            return f"conda run -n {self.conda_env} python"
        return self.python_path

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典 (不包含敏感信息)"""
        return {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_method": self.auth_method,
            "remote_workspace": self.remote_workspace,
            "python_path": self.python_path,
            "conda_env": self.conda_env,
            "gpu_required": self.gpu_required,
            "gpu_device": self.gpu_device,
            "experiment_timeout_minutes": self.experiment_timeout_minutes,
        }


@dataclass
class DeploymentProfile:
    """部署配置文件

    用于存储和加载多个服务器配置。
    """

    name: str
    remote_config: RemoteConfig
    description: str = ""

    # 代码同步配置
    exclude_patterns: List[str] = field(default_factory=lambda: [
        ".git",
        "__pycache__",
        "*.pyc",
        ".venv",
        "venv",
        "node_modules",
        "*.log",
        ".ipynb_checkpoints",
    ])

    # 依赖安装配置
    install_requirements: bool = True
    pip_extra_index: Optional[str] = None  # 额外的 pip 镜像

    def to_dict(self) -> Dict[str, Any]:
        config = self.remote_config.to_dict()
        config["name"] = self.name
        config["description"] = self.description
        config["exclude_patterns"] = self.exclude_patterns
        config["install_requirements"] = self.install_requirements
        config["pip_extra_index"] = self.pip_extra_index
        return config

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeploymentProfile":
        """从字典创建配置"""
        remote_config = RemoteConfig(**{
            k: v for k, v in data.items()
            if k in RemoteConfig.__dataclass_fields__
        })
        return cls(
            name=data["name"],
            remote_config=remote_config,
            description=data.get("description", ""),
            exclude_patterns=data.get("exclude_patterns", []),
            install_requirements=data.get("install_requirements", True),
            pip_extra_index=data.get("pip_extra_index"),
        )


def load_deployment_profile(config_path: str) -> DeploymentProfile:
    """从 YAML 文件加载部署配置

    Args:
        config_path: 配置文件路径

    Returns:
        DeploymentProfile 实例
    """
    import yaml

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    return DeploymentProfile.from_dict(data)


def save_deployment_profile(profile: DeploymentProfile, config_path: str) -> None:
    """保存部署配置到 YAML 文件

    Args:
        profile: 部署配置
        config_path: 配置文件路径
    """
    import yaml

    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)

    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(profile.to_dict(), f, default_flow_style=False, allow_unicode=True)
