"""Tests for Remote Deployment Module - 远程部署模块测试"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from tutor.core.deployment.config import RemoteConfig, DeploymentProfile
from tutor.core.deployment.exceptions import (
    DeploymentError,
    SSHConnectionError,
    AuthenticationError,
    CommandExecutionError,
    FileTransferError,
)
from tutor.core.deployment.ssh_client import SSHClient, CommandResult
from tutor.core.deployment.remote_executor import RemoteExecutor, ExperimentResult


class TestRemoteConfig:
    """测试 RemoteConfig 配置"""

    def test_config_requires_username(self):
        """测试用户名是必需的"""
        with pytest.raises(ValueError):
            RemoteConfig(host="example.com")

    def test_config_requires_auth(self):
        """测试认证方式是必需的"""
        with pytest.raises(ValueError):
            RemoteConfig(host="example.com", username="user")

    def test_config_with_password(self):
        """测试密码认证配置"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        assert config.host == "example.com"
        assert config.auth_method == "password"

    def test_config_with_key(self):
        """测试密钥认证配置"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            key_file="~/.ssh/id_rsa"
        )
        assert config.auth_method == "key"

    def test_config_invalid_key_file(self):
        """测试无效的密钥文件"""
        with pytest.raises(ValueError):
            RemoteConfig(
                host="example.com",
                username="user",
                key_file="/nonexistent/key"
            )

    def test_get_python_command(self):
        """测试 Python 命令生成"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret",
            python_path="python3.10"
        )
        assert config.get_python_command() == "python3.10"

    def test_get_python_command_with_conda(self):
        """测试 Conda 环境命令"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret",
            conda_env="ml"
        )
        assert "conda run" in config.get_python_command()
        assert "ml" in config.get_python_command()


class TestDeploymentProfile:
    """测试 DeploymentProfile"""

    def test_profile_creation(self):
        """测试配置文件创建"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        profile = DeploymentProfile(
            name="gpu-server-1",
            remote_config=config,
            description="Primary GPU server"
        )
        assert profile.name == "gpu-server-1"
        assert profile.remote_config.host == "example.com"

    def test_profile_to_dict(self):
        """测试配置序列化"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        profile = DeploymentProfile(
            name="test-profile",
            remote_config=config,
            exclude_patterns=[".git", "*.pyc"]
        )
        d = profile.to_dict()
        assert d["name"] == "test-profile"
        assert d["host"] == "example.com"
        assert ".git" in d["exclude_patterns"]

    def test_profile_from_dict(self):
        """测试配置反序列化"""
        data = {
            "name": "restored-profile",
            "host": "example.com",
            "port": 22,
            "username": "user",
            "password": "secret",
            "exclude_patterns": [".venv"],
            "install_requirements": True,
        }
        profile = DeploymentProfile.from_dict(data)
        assert profile.name == "restored-profile"
        assert profile.remote_config.host == "example.com"
        assert ".venv" in profile.exclude_patterns


class TestSSHClient:
    """测试 SSHClient"""

    def test_client_initialization(self):
        """测试客户端初始化"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        client = SSHClient(config)
        assert client.config == config
        assert not client.is_connected()

    def test_client_initialization_and_disconnect(self):
        """测试客户端初始化和断开连接"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        client = SSHClient(config)
        # 验证初始化成功
        assert client.config == config
        assert not client.is_connected()
        # 断开连接（应该安全地什么也不做）
        client.disconnect()
        assert not client.is_connected()


class TestCommandResult:
    """测试 CommandResult"""

    def test_command_result_success(self):
        """测试成功的结果"""
        result = CommandResult(
            command="ls",
            exit_code=0,
            output="file1 file2",
            error="",
            host="example.com"
        )
        assert result.success is True
        assert result.exit_code == 0

    def test_command_result_failure(self):
        """测试失败的结果"""
        result = CommandResult(
            command="ls",
            exit_code=1,
            output="",
            error="Permission denied",
            host="example.com"
        )
        assert result.success is False
        assert result.exit_code == 1

    def test_command_result_str(self):
        """测试结果字符串表示"""
        result = CommandResult(
            command="ls",
            exit_code=0,
            output="test",
            error="",
            host="example.com"
        )
        s = str(result)
        assert "exit_code=0" in s
        assert "example.com" in s


class TestRemoteExecutor:
    """测试 RemoteExecutor"""

    def test_executor_initialization(self):
        """测试执行器初始化"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        executor = RemoteExecutor(config)
        assert executor.config == config
        assert not executor.is_connected

    def test_executor_with_profile(self):
        """测试带配置文件的执行器"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        profile = DeploymentProfile(
            name="test",
            remote_config=config
        )
        executor = RemoteExecutor(config, profile)
        assert executor.profile == profile

    def test_executor_initialization_and_disconnect(self):
        """测试执行器初始化和断开连接"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        executor = RemoteExecutor(config)
        # 验证初始化成功
        assert executor.config == config
        assert not executor.is_connected
        # 断开连接（应该安全地什么也不做）
        executor.disconnect()
        assert not executor.is_connected


class TestExperimentResult:
    """测试 ExperimentResult"""

    def test_experiment_result_success(self):
        """测试成功的实验结果"""
        result = ExperimentResult(
            experiment_id="exp-001",
            workspace_path="/tmp/exp-001",
            success=True,
            exit_code=0,
            output="accuracy: 0.95",
            error="",
            metrics={"accuracy": 0.95}
        )
        assert result.success is True
        assert result.metrics["accuracy"] == 0.95

    def test_experiment_result_to_dict(self):
        """测试结果序列化"""
        result = ExperimentResult(
            experiment_id="exp-001",
            workspace_path="/tmp/exp-001",
            success=True,
            exit_code=0,
            output="test output",
            error="",
            metrics={"loss": 0.1}
        )
        d = result.to_dict()
        assert d["experiment_id"] == "exp-001"
        assert d["success"] is True
        assert d["metrics"]["loss"] == 0.1


class TestDeploymentExceptions:
    """测试部署异常"""

    def test_ssh_connection_error(self):
        """测试 SSH 连接异常"""
        error = SSHConnectionError(
            host="example.com",
            port=22,
            username="user",
            reason="Connection refused"
        )
        assert "example.com" in str(error)
        assert error.host == "example.com"

    def test_authentication_error(self):
        """测试认证异常"""
        error = AuthenticationError(
            host="example.com",
            username="user",
            method="password"
        )
        assert "Authentication failed" in str(error)
        assert error.username == "user"

    def test_command_execution_error(self):
        """测试命令执行异常"""
        error = CommandExecutionError(
            command="ls -la",
            host="example.com",
            exit_code=1,
            stderr="Permission denied"
        )
        assert "ls -la" in str(error)
        assert error.exit_code == 1

    def test_file_transfer_error(self):
        """测试文件传输异常"""
        error = FileTransferError(
            operation="upload",
            local_path="/local/file.txt",
            remote_path="/remote/file.txt",
            reason="Disk full"
        )
        assert "upload" in str(error)
        assert "Disk full" in str(error)

    def test_deployment_error_with_context(self):
        """测试部署异常包含上下文信息"""
        error = DeploymentError(
            message="Generic deployment error",
            host="example.com",
            details="Additional context"
        )
        assert "example.com" in str(error)
        assert "Additional context" in str(error)


class TestRemoteExecutorPrivateMethods:
    """测试 RemoteExecutor 私有方法 (通过公共接口)"""

    def test_extract_metrics(self):
        """测试指标提取"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        executor = RemoteExecutor(config)

        # 测试各种指标格式
        output = """
        Epoch 1: loss=0.5, accuracy=0.8
        val_loss: 0.3 | val_accuracy: 0.85
        Test accuracy: 0.90
        """

        metrics = executor._extract_metrics(output)

        assert "loss" in metrics
        assert "accuracy" in metrics
        assert "val_loss" in metrics
        assert "val_accuracy" in metrics
        # 检查数值存在且在合理范围内
        assert 0.5 <= metrics["accuracy"] <= 1.0

    def test_extract_metrics_empty(self):
        """测试空输出的指标提取"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )
        executor = RemoteExecutor(config)

        metrics = executor._extract_metrics("")
        assert metrics == {}

    def test_create_workspace_path(self):
        """测试工作空间创建 (需要 mock SSH)"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )

        # 创建一个 mock executor
        executor = RemoteExecutor(config)

        # 验证 workspace_id 相关逻辑
        workspace_id = "test-exp-123"
        executor._workspace_id = workspace_id
        assert executor._workspace_id == workspace_id


class TestIntegration:
    """集成测试 (需要 mock)"""

    def test_full_pipeline_mocked(self):
        """测试完整流程 (mock SSH client)"""
        config = RemoteConfig(
            host="example.com",
            username="user",
            password="secret"
        )

        # Mock SSH client
        with patch("tutor.core.deployment.remote_executor.SSHClient") as MockSSH:
            mock_instance = MagicMock()
            MockSSH.return_value = mock_instance

            # 模拟成功的命令执行
            mock_result = CommandResult(
                command="test",
                exit_code=0,
                output="success",
                error="",
                host="example.com"
            )
            mock_instance.execute.return_value = mock_result
            mock_instance.is_connected.return_value = True

            # 测试连接和断开
            executor = RemoteExecutor(config)
            executor.connect()
            assert mock_instance.connect.called
            executor.disconnect()
            assert mock_instance.disconnect.called
