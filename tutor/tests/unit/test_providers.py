"""Model Provider 单元测试

测试多 Provider 架构：
- Provider 抽象基类
- OpenAI Provider
- Anthropic Provider
- Azure Provider
- Local Provider (Ollama/LM Studio)
- Provider Router (故障切换/负载均衡)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import uuid


class TestBaseProvider:
    """Provider 抽象基类测试"""

    def test_provider_base_class_exists(self):
        """BaseProvider 抽象类应该存在"""
        from tutor.core.providers.base import BaseProvider
        assert BaseProvider is not None

    def test_provider_is_abstract(self):
        """BaseProvider 应该是抽象类，不能直接实例化"""
        from tutor.core.providers.base import BaseProvider
        with pytest.raises(TypeError):
            BaseProvider()

    def test_provider_required_methods(self):
        """Provider 必须实现 required 方法"""
        from tutor.core.providers.base import BaseProvider
        import inspect

        # 检查抽象方法
        abstract_methods = {
            name for name, method in inspect.getmembers(BaseProvider)
            if getattr(method, '__isabstractmethod__', False)
        }

        assert 'chat' in abstract_methods
        assert 'validate_connection' in abstract_methods
        assert 'get_provider_name' in abstract_methods

    def test_provider_chat_returns_string(self):
        """chat 方法应该返回字符串"""
        from tutor.core.providers.base import BaseProvider

        class MockProvider(BaseProvider):
            def get_provider_name(self) -> str:
                return "mock"

            def chat(self, model: str, messages: List[Dict], **kwargs) -> str:
                return "mock response"

            def validate_connection(self) -> bool:
                return True

        provider = MockProvider(api_key="test-key")
        result = provider.chat("gpt-4", [{"role": "user", "content": "hello"}])
        assert isinstance(result, str)


class TestOpenAIProvider:
    """OpenAI Provider 测试"""

    def test_provider_name(self):
        """OpenAI Provider 名称应该是 'openai'"""
        from tutor.core.providers.openai import OpenAIProvider
        provider = OpenAIProvider(api_key="test-key")
        assert provider.get_provider_name() == "openai"

    def test_chat_request_format(self):
        """OpenAI 请求格式应该是 chat completions"""
        from tutor.core.providers.openai import OpenAIProvider

        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Hello!"}}]
            }
            mock_post.return_value = mock_response

            provider = OpenAIProvider(api_key="sk-test")
            result = provider.chat("gpt-3.5-turbo", [{"role": "user", "content": "Hi"}])

            assert result == "Hello!"
            mock_post.assert_called_once()

            # 验证请求格式
            call_args = mock_post.call_args
            assert "chat/completions" in call_args[0][0]
            assert call_args[1]["headers"]["Authorization"] == "Bearer sk-test"

    def test_validate_connection_success(self):
        """validate_connection 应该在连接成功时返回 True"""
        from tutor.core.providers.openai import OpenAIProvider

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            provider = OpenAIProvider(api_key="sk-test")
            assert provider.validate_connection() is True

    def test_validate_connection_failure(self):
        """validate_connection 应该在连接失败时返回 False"""
        from tutor.core.providers.openai import OpenAIProvider

        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Connection failed")

            provider = OpenAIProvider(api_key="sk-test")
            assert provider.validate_connection() is False


class TestAnthropicProvider:
    """Anthropic Provider 测试"""

    def test_provider_name(self):
        """Anthropic Provider 名称应该是 'anthropic'"""
        from tutor.core.providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key="sk-test")
        assert provider.get_provider_name() == "anthropic"

    def test_chat_request_format(self):
        """Anthropic 请求格式应该转换为 Anthropic API 格式"""
        from tutor.core.providers.anthropic import AnthropicProvider

        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "content": [{"text": "Hello!"}]
            }
            mock_post.return_value = mock_response

            provider = AnthropicProvider(api_key="sk-test")
            result = provider.chat("claude-3-sonnet-20240229", [
                {"role": "user", "content": "Hi"}
            ])

            assert result == "Hello!"
            mock_post.assert_called_once()

            # 验证 Anthropic API 格式
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert "anthropic-version" in call_args[1]["headers"]  # version is in headers
            assert payload["max_tokens"] > 0


class TestAzureProvider:
    """Azure OpenAI Provider 测试"""

    def test_provider_name(self):
        """Azure Provider 名称应该是 'azure'"""
        from tutor.core.providers.azure import AzureProvider
        provider = AzureProvider(api_key="test-key", deployment_name="gpt-4-turbo")
        assert provider.get_provider_name() == "azure"

    def test_chat_request_uses_deployment(self):
        """Azure 请求应该使用 deployment_name 而非 model"""
        from tutor.core.providers.azure import AzureProvider

        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Hello!"}}]
            }
            mock_post.return_value = mock_response

            provider = AzureProvider(
                api_key="test-key",
                api_base="https://xxx.openai.azure.com",
                deployment_name="gpt-4-turbo"
            )
            result = provider.chat("gpt-4-turbo", [{"role": "user", "content": "Hi"}])

            assert result == "Hello!"
            call_args = mock_post.call_args
            # Azure 使用 deployment_name
            payload = call_args[1]["json"]
            assert payload["deployment"] == "gpt-4-turbo"


class TestLocalProvider:
    """Local Provider (Ollama/LM Studio) 测试"""

    def test_provider_name(self):
        """Local Provider 名称应该是 'local'"""
        from tutor.core.providers.local import LocalProvider
        provider = LocalProvider(api_base="http://localhost:11434")
        assert provider.get_provider_name() == "local"

    def test_chat_request_format(self):
        """Local Provider 请求格式应该兼容 OpenAI API"""
        from tutor.core.providers.local import LocalProvider

        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Hello from local!"}}]
            }
            mock_post.return_value = mock_response

            provider = LocalProvider(api_base="http://localhost:11434/v1")
            result = provider.chat("llama2", [{"role": "user", "content": "Hi"}])

            assert result == "Hello from local!"


class TestProviderRouter:
    """Provider 路由测试"""

    def test_router_with_single_provider(self):
        """单 Provider 路由"""
        from tutor.core.providers.router import ProviderRouter, RouterConfig

        @ProviderRouter.register_provider("test")
        class MockProvider:
            def __init__(self, **kwargs):
                self.api_key = kwargs.get("api_key", "")
                self.called = False

            def get_provider_name(self) -> str:
                return "test"

            def chat(self, model: str, messages: List[Dict], **kwargs) -> str:
                self.called = True
                return f"response from test:{model}"

            def validate_connection(self) -> bool:
                return True

        router = ProviderRouter(
            providers=[MockProvider(api_key="test")],
            config=RouterConfig()
        )

        result = router.chat("auto", [{"role": "user", "content": "hello"}])
        assert "test" in result

    def test_router_failover_on_failure(self):
        """主 Provider 失败时自动切换到备用"""
        from tutor.core.providers.router import ProviderRouter, RouterConfig

        call_order = []

        class PrimaryProvider:
            def __init__(self, **kwargs):
                self.api_key = kwargs.get("api_key", "")

            def get_provider_name(self) -> str:
                return "primary"

            def chat(self, model: str, messages: List[Dict], **kwargs) -> str:
                call_order.append("primary")
                raise Exception("Primary failed")

            def validate_connection(self) -> bool:
                return False

        class FallbackProvider:
            def __init__(self, **kwargs):
                self.api_key = kwargs.get("api_key", "")

            def get_provider_name(self) -> str:
                return "fallback"

            def chat(self, model: str, messages: List[Dict], **kwargs) -> str:
                call_order.append("fallback")
                return "fallback response"

            def validate_connection(self) -> bool:
                return True

        router = ProviderRouter(
            providers=[
                PrimaryProvider(api_key="primary-key"),
                FallbackProvider(api_key="fallback-key")
            ],
            config=RouterConfig(fallback_enabled=True)
        )

        result = router.chat("auto", [{"role": "user", "content": "hello"}])

        assert result == "fallback response"
        assert "primary" in call_order
        assert "fallback" in call_order

    def test_router_load_balance(self):
        """负载均衡策略"""
        from tutor.core.providers.router import ProviderRouter, RouterConfig

        class LBProvider1:
            def __init__(self, **kwargs):
                self.api_key = kwargs.get("api_key", "")

            def get_provider_name(self) -> str:
                return "lb1"

            def chat(self, model: str, messages: List[Dict], **kwargs) -> str:
                return "lb1-response"

            def validate_connection(self) -> bool:
                return True

        class LBProvider2:
            def __init__(self, **kwargs):
                self.api_key = kwargs.get("api_key", "")

            def get_provider_name(self) -> str:
                return "lb2"

            def chat(self, model: str, messages: List[Dict], **kwargs) -> str:
                return "lb2-response"

            def validate_connection(self) -> bool:
                return True

        router = ProviderRouter(
            providers=[
                LBProvider1(api_key="key1"),
                LBProvider2(api_key="key2")
            ],
            config=RouterConfig(strategy="loadbalance")
        )

        # 连续调用应该交替使用不同 provider
        results = set()
        for _ in range(6):
            r = router.chat("auto", [{"role": "user", "content": "hello"}])
            results.add(r)

        # 两种响应都应该出现
        assert len(results) == 2


class TestProviderConfig:
    """Provider 配置测试"""

    def test_provider_config_dataclass(self):
        """ProviderConfig 应该正确存储配置"""
        from tutor.core.providers.base import ProviderConfig

        config = ProviderConfig(
            name="openai",
            api_key="sk-test",
            api_base="https://api.openai.com/v1",
            priority=1
        )

        assert config.name == "openai"
        assert config.api_key == "sk-test"
        assert config.priority == 1

    def test_provider_config_priority_order(self):
        """Provider 应该按 priority 排序"""
        from tutor.core.providers.base import ProviderConfig

        configs = [
            ProviderConfig(name="low", priority=3),
            ProviderConfig(name="high", priority=1),
            ProviderConfig(name="medium", priority=2),
        ]

        sorted_configs = sorted(configs)
        assert [c.name for c in sorted_configs] == ["high", "medium", "low"]
