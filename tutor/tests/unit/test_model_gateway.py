"""Model Gateway 单元测试

测试覆盖率目标：
- 正常调用流程
- 错误处理（超时、API错误、无效响应）
- 配置加载
- 连接验证
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from requests.exceptions import Timeout, RequestException

from tutor.core.model import ModelGateway, ModelError, ModelConfig


class TestModelGateway:
    """ModelGateway 测试类"""
    
    def test_init_with_valid_config(self, tmp_path):
        """测试：使用有效配置初始化"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    test_model: gpt-4
""")
        gateway = ModelGateway(str(config_file))
        assert gateway.config.provider == "openai"
        assert gateway.models["test_model"] == "gpt-4"
    
    def test_init_missing_config_raises(self):
        """测试：配置文件不存在时抛出异常"""
        with pytest.raises(ValueError):
            ModelGateway("nonexistent.yaml")
    
    def test_chat_success(self, tmp_path):
        """测试：聊天调用成功返回"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    test_model: gpt-4
""")

        gateway = ModelGateway(str(config_file))

        # Mock requests.post
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello, I'm GPT-4"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('requests.post', return_value=mock_response):
            result = gateway.chat("test_model", [{"role": "user", "content": "Hello"}])
            assert result == "Hello, I'm GPT-4"
    
    def test_chat_unknown_model_raises(self, tmp_path):
        """测试：调用未知模型抛出异常"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    known_model: gpt-4
""")
        
        gateway = ModelGateway(str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            gateway.chat("unknown_model", [{"role": "user", "content": "Hello"}])
        assert "Unknown model name" in str(exc_info.value)
    
    def test_chat_timeout_raises_model_error(self, tmp_path):
        """测试：超时抛出ModelError"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    test_model: gpt-4
""")
        
        gateway = ModelGateway(str(config_file))
        
        with patch('requests.post', side_effect=Timeout()):
            with pytest.raises(ModelError) as exc_info:
                gateway.chat("test_model", [{"role": "user", "content": "Hello"}])
            assert "Timeout" in str(exc_info.value)
    
    def test_chat_http_error_raises_model_error(self, tmp_path):
        """测试：HTTP错误抛出ModelError"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    test_model: gpt-4
""")

        gateway = ModelGateway(str(config_file))

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = RequestException("401 Unauthorized")

        with patch('requests.post', return_value=mock_response):
            with pytest.raises(ModelError):
                gateway.chat("test_model", [{"role": "user", "content": "Hello"}])
    
    def test_chat_invalid_response_format_raises(self, tmp_path):
        """测试：无效响应格式抛出ModelError"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    test_model: gpt-4
""")

        gateway = ModelGateway(str(config_file))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "invalid"}
        mock_response.raise_for_status = MagicMock()

        with patch('requests.post', return_value=mock_response):
            with pytest.raises(ModelError):
                gateway.chat("test_model", [{"role": "user", "content": "Hello"}])
    
    def test_validate_connection_success(self, tmp_path):
        """测试：连接验证成功"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    test_model: gpt-4
""")
        
        gateway = ModelGateway(str(config_file))
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch('requests.get', return_value=mock_response):
            assert gateway.validate_connection() is True
    
    def test_validate_connection_failure(self, tmp_path):
        """测试：连接验证失败"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
model:
  provider: openai
  api_base: https://api.openai.com/v1
  api_key: test-key
  models:
    test_model: gpt-4
""")
        
        gateway = ModelGateway(str(config_file))
        
        with patch('requests.get', side_effect=RequestException("Network error")):
            assert gateway.validate_connection() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
