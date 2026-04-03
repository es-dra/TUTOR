"""ModelGateway 单元测试"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tutor.core.model import ModelGateway, ModelConfig, ModelError


class TestModelConfig:
    """测试 ModelConfig 数据类"""

    def test_default_values(self):
        """测试默认配置"""
        config = ModelConfig()
        assert config.provider == "openai"
        assert config.api_base == "https://api.openai.com/v1"
        assert config.api_key == ""
        assert config.models == {}

    def test_custom_values(self):
        """测试自定义配置"""
        config = ModelConfig(
            provider="anthropic",
            api_base="https://api.anthropic.com",
            api_key="sk-test-key",
            models={"default": "claude-3"}
        )
        assert config.provider == "anthropic"
        assert config.api_base == "https://api.anthropic.com"
        assert config.api_key == "sk-test-key"
        assert config.models == {"default": "claude-3"}

    def test_to_dict(self):
        """测试转换为字典"""
        config = ModelConfig(provider="test", api_key="key")
        d = config.to_dict()
        assert isinstance(d, dict)
        assert d["provider"] == "test"
        assert d["api_key"] == "key"

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "provider": "openai",
            "api_base": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "models": {"default": "gpt-4"}
        }
        config = ModelConfig.from_dict(data)
        assert config.provider == "openai"
        assert config.api_key == "sk-test"
        assert config.models == {"default": "gpt-4"}


class TestModelGateway:
    """测试 ModelGateway 类"""

    def test_init_with_dict(self):
        """测试用字典初始化"""
        config = {
            "provider": "openai",
            "api_base": "https://api.openai.com/v1",
            "api_key": "sk-test-key",
            "models": {"default": "gpt-3.5-turbo"}
        }
        gateway = ModelGateway(config)
        assert gateway.config.provider == "openai"
        assert gateway.api_key == "sk-test-key"

    def test_init_with_model_config(self):
        """测试用 ModelConfig 对象初始化"""
        config = ModelConfig(
            provider="anthropic",
            api_key="sk-ant-key",
            models={"default": "claude-3"}
        )
        gateway = ModelGateway(config)
        assert gateway.config.provider == "anthropic"
        assert gateway.api_key == "sk-ant-key"

    def test_init_with_none(self):
        """测试无配置初始化（使用默认值）"""
        # 需要确保没有环境变量影响
        with patch.dict(os.environ, {}, clear=True):
            gateway = ModelGateway(None)
            assert gateway.config.provider == "openai"
            assert gateway.config.api_base == "https://api.openai.com/v1"

    def test_init_with_api_key_only(self):
        """测试只提供 API key"""
        gateway = ModelGateway("sk-test-key")
        assert gateway.api_key == "sk-test-key"

    def test_init_with_url_only(self):
        """测试只提供 URL"""
        gateway = ModelGateway("https://api.openai.com/v1")
        assert gateway.api_base == "https://api.openai.com/v1"

    def test_list_models(self):
        """测试列出模型"""
        gateway = ModelGateway({"models": {"a": "model-a", "b": "model-b"}})
        models = gateway.list_models()
        assert "a" in models
        assert "b" in models

    def test_chat_unknown_model_uses_default(self):
        """测试未知模型自动使用默认模型"""
        gateway = ModelGateway({
            "api_key": "sk-test",
            "models": {"default": "gpt-3.5-turbo", "other": "gpt-4"}
        })

        # unknown_model 不存在，应该使用 default
        with patch('tutor.core.model.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "test response"}}]
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            result = gateway.chat("unknown_model", [{"role": "user", "content": "hello"}])
            assert result == "test response"
            # 验证使用了默认模型
            call_args = mock_post.call_args
            assert "gpt-3.5-turbo" in str(call_args)

    def test_chat_unknown_model_no_default_raises(self):
        """测试未知模型且无默认模型时抛出异常"""
        gateway = ModelGateway({
            "api_key": "sk-test",
            "models": {"specific": "gpt-4"}  # 没有 default
        })

        with pytest.raises(ValueError, match="Unknown model name"):
            gateway.chat("unknown_model", [{"role": "user", "content": "hello"}])

    @patch('tutor.core.model.requests.post')
    def test_chat_success(self, mock_post):
        """测试成功调用"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gateway = ModelGateway({
            "api_key": "sk-test",
            "api_base": "https://api.openai.com/v1",
            "models": {"default": "gpt-3.5-turbo"}
        })

        result = gateway.chat("default", [{"role": "user", "content": "hi"}])
        assert result == "Hello!"
        mock_post.assert_called_once()

    @patch('tutor.core.model.requests.post')
    def test_chat_timeout(self, mock_post):
        """测试超时处理"""
        from requests.exceptions import Timeout
        mock_post.side_effect = Timeout()

        gateway = ModelGateway({
            "api_key": "sk-test",
            "models": {"default": "gpt-3.5-turbo"}
        })

        with pytest.raises(ModelError, match="Timeout"):
            gateway.chat("default", [{"role": "user", "content": "hi"}])

    @patch('tutor.core.model.requests.post')
    def test_chat_request_error(self, mock_post):
        """测试请求错误处理"""
        from requests.exceptions import RequestException
        mock_post.side_effect = RequestException("Connection failed")

        gateway = ModelGateway({
            "api_key": "sk-test",
            "models": {"default": "gpt-3.5-turbo"}
        })

        with pytest.raises(ModelError, match="Model call failed"):
            gateway.chat("default", [{"role": "user", "content": "hi"}])

    @patch('tutor.core.model.requests.post')
    def test_chat_invalid_response(self, mock_post):
        """测试无效响应格式"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid": "format"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gateway = ModelGateway({
            "api_key": "sk-test",
            "models": {"default": "gpt-3.5-turbo"}
        })

        with pytest.raises(ModelError, match="Invalid response format"):
            gateway.chat("default", [{"role": "user", "content": "hi"}])

    @patch('tutor.core.model.requests.get')
    def test_validate_connection_success(self, mock_get):
        """测试连接验证成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        gateway = ModelGateway({"api_key": "sk-test"})
        assert gateway.validate_connection() is True

    @patch('tutor.core.model.requests.get')
    def test_validate_connection_failure(self, mock_get):
        """测试连接验证失败"""
        from requests.exceptions import RequestException
        mock_get.side_effect = RequestException("Failed")

        gateway = ModelGateway({"api_key": "sk-test"})
        assert gateway.validate_connection() is False

    def test_validate_connection_no_api_key(self):
        """测试无 API key 时验证失败"""
        gateway = ModelGateway({"api_key": ""})
        assert gateway.validate_connection() is False


class TestModelError:
    """测试 ModelError 异常类"""

    def test_raise_and_catch(self):
        """测试异常抛出和捕获"""
        with pytest.raises(ModelError):
            raise ModelError("Test error")

    def test_error_message(self):
        """测试错误消息"""
        error = ModelError("Specific error")
        assert str(error) == "Specific error"
