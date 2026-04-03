"""Tests for CrossModelDebater - 跨模型辩论框架测试"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from tutor.core.debate.cross_model_debater import (
    CrossModelDebater,
    ModelGatewayAdapter,
    DebateResult,
    DebateTurn,
    ModelResponse,
    DebateRole,
    create_cross_model_debater,
)
from tutor.core.debate.model_config import (
    DebateModelConfig,
    ModuleModelConfig,
    ModelAssignment,
    RoleModelAssignment,
    get_default_debate_config,
    create_user_config,
    MODEL_VENDOR_MAP,
)


class MockModelGateway:
    """Mock ModelGateway for testing"""

    def __init__(self):
        self.chat_call_count = 0
        self.last_model_name = None
        self.last_messages = None

    def chat(self, model_name, messages, temperature=0.7, max_tokens=2000):
        self.chat_call_count += 1
        self.last_model_name = model_name
        self.last_messages = messages

        # Return mock responses based on model
        if "claude" in model_name.lower():
            return "Claude: This is a creative and innovative response about the research topic."
        elif "gpt" in model_name.lower() or "gpt4" in model_name.lower():
            return "GPT: This is a thoughtful and analytical response about the research topic."
        elif "gemini" in model_name.lower():
            return "Gemini: This is a comprehensive and balanced response about the research topic."
        else:
            return f"Mock response from {model_name}."

    def list_models(self):
        return ["gpt-4o", "claude-sonnet-4", "gemini-2-5-pro"]


@pytest.fixture
def mock_gateway():
    return MockModelGateway()


@pytest.fixture
def default_config():
    return get_default_debate_config()


class TestModelGatewayAdapter:
    """测试ModelGatewayAdapter"""

    def test_resolve_model_alias(self, mock_gateway):
        adapter = ModelGatewayAdapter(mock_gateway)

        # Test alias resolution
        assert adapter._resolve_model_name("claude") == "claude-sonnet-4-20250514"
        assert adapter._resolve_model_name("gpt4") == "gpt-4o"
        assert adapter._resolve_model_name("gemini") == "gemini-2-5-pro-preview-06-05"

    def test_resolve_exact_model(self, mock_gateway):
        adapter = ModelGatewayAdapter(mock_gateway)
        assert adapter._resolve_model_name("gpt-4o") == "gpt-4o"

    def test_resolve_unknown_model(self, mock_gateway):
        adapter = ModelGatewayAdapter(mock_gateway)
        # Should fallback to first available
        result = adapter._resolve_model_name("unknown-model-xyz")
        assert result in mock_gateway.list_models()


class TestModelAssignment:
    """测试模型分配"""

    def test_single_model_assignment(self):
        assignment = ModelAssignment(model_id="gpt-4o", temperature=0.7)
        assert assignment.model_id == "gpt-4o"
        assert assignment.temperature == 0.7
        assert assignment.vendor == "openai"

    def test_model_assignment_with_custom_params(self):
        assignment = ModelAssignment(
            model_id="claude-sonnet-4",
            temperature=0.5,
            max_tokens=3000,
            custom_prompt_suffix="Be more creative."
        )
        assert assignment.max_tokens == 3000
        assert assignment.custom_prompt_suffix == "Be more creative."


class TestRoleModelAssignment:
    """测试角色模型分配"""

    def test_role_assignment_primary_model(self):
        models = [
            ModelAssignment(model_id="gpt-4o"),
            ModelAssignment(model_id="claude-sonnet-4"),
        ]
        assignment = RoleModelAssignment(role=DebateRole.INNOVATOR, models=models)
        assert assignment.primary_model.model_id == "gpt-4o"
        assert assignment.is_heterogeneous is True
        assert assignment.is_single_model is False

    def test_single_model_role_assignment(self):
        models = [ModelAssignment(model_id="gpt-4o")]
        assignment = RoleModelAssignment(role=DebateRole.SKEPTIC, models=models)
        assert assignment.primary_model.model_id == "gpt-4o"
        assert assignment.is_single_model is True
        assert assignment.is_heterogeneous is False


class TestModuleModelConfig:
    """测试模块配置"""

    def test_get_role(self, default_config):
        innovator = default_config.get_role(DebateRole.INNOVATOR)
        assert innovator is not None
        assert innovator.role == DebateRole.INNOVATOR

    def test_get_role_not_found(self, default_config):
        # Try to get a role that's not assigned
        nonexistent = default_config.get_role(DebateRole.CRITIC)
        # CRITIC might not be in default config
        # Just verify it doesn't crash

    def test_get_unique_vendors(self, default_config):
        vendors = default_config.get_unique_vendors()
        assert isinstance(vendors, list)


class TestCrossModelDebater:
    """测试CrossModelDebater主类"""

    def test_debater_initialization(self, mock_gateway, default_config):
        debater = CrossModelDebater(mock_gateway, default_config)
        assert debater.debate_id is not None
        assert debater.mode in ["heterogeneous", "single_model"]

    def test_mode_detection_heterogeneous(self, mock_gateway):
        """测试异构模式检测"""
        config = create_user_config("test", {
            "innovator": ["claude-sonnet-4"],
            "skeptic": ["gpt-4o"],
            "synthesizer": ["gemini-2-5-pro"],
        })
        debater = CrossModelDebater(mock_gateway, config)
        assert debater.mode == "heterogeneous"

    def test_mode_detection_single_model(self, mock_gateway):
        """测试单模型模式检测"""
        config = create_user_config("test", {
            "innovator": ["gpt-4o"],
            "skeptic": ["gpt-4o"],  # Same model
            "synthesizer": ["gpt-4o"],
        })
        debater = CrossModelDebater(mock_gateway, config)
        assert debater.mode == "single_model"

    def test_debate_sync_runs(self, mock_gateway, default_config):
        """测试同步辩论运行"""
        debater = CrossModelDebater(mock_gateway, default_config)
        result = debater.debate_sync(
            topic="Should we use transformers for time series forecasting?",
            rounds=1
        )

        assert isinstance(result, DebateResult)
        assert result.topic == "Should we use transformers for time series forecasting?"
        assert result.mode in ["heterogeneous", "single_model"]

    def test_debate_result_structure(self, mock_gateway, default_config):
        """测试辩论结果结构"""
        debater = CrossModelDebater(mock_gateway, default_config)
        result = debater.debate_sync(
            topic="Test topic",
            rounds=1
        )

        assert result.debate_id is not None
        assert result.success is True
        assert result.total_rounds >= 0
        assert isinstance(result.models_used, list)

    def test_debate_with_custom_debate_id(self, mock_gateway, default_config):
        """测试自定义辩论ID"""
        debater = CrossModelDebater(
            mock_gateway,
            default_config,
            debate_id="custom-debate-123"
        )
        assert debater.debate_id == "custom-debate-123"


class TestCrossModelDebaterRoles:
    """测试辩论角色"""

    def test_role_prompts_exist(self, mock_gateway, default_config):
        """测试角色提示词是否存在"""
        debater = CrossModelDebater(mock_gateway, default_config)

        for role in [DebateRole.INNOVATOR, DebateRole.SKEPTIC, DebateRole.SYNTHESIZER]:
            prompt = debater._get_role_prompt(role)
            assert prompt is not None
            assert len(prompt) > 0

    def test_custom_prompts_override(self, mock_gateway, default_config):
        """测试自定义提示词可以覆盖默认"""
        custom_prompts = {
            "innovator": "You are a revolutionary researcher."
        }
        debater = CrossModelDebater(
            mock_gateway,
            default_config,
            custom_prompts=custom_prompts
        )
        assert debater._get_role_prompt(DebateRole.INNOVATOR) == "You are a revolutionary researcher."


class TestDebateResult:
    """测试辩论结果数据结构"""

    def test_debate_result_to_dict(self):
        """测试结果序列化"""
        result = DebateResult(
            debate_id="test-123",
            topic="Test topic",
            success=True,
            mode="heterogeneous",
            models_used=["gpt-4o", "claude-sonnet-4"],
            vendors_used=["openai", "anthropic"],
        )

        result_dict = result.to_dict()
        assert result_dict["debate_id"] == "test-123"
        assert result_dict["success"] is True
        assert len(result_dict["models_used"]) == 2


class TestModelVendorMap:
    """测试模型厂商映射"""

    def test_vendor_map_contains_key_vendors(self):
        """测试厂商映射包含主要厂商"""
        assert "anthropic" in MODEL_VENDOR_MAP.values() or any("claude" in v for v in MODEL_VENDOR_MAP.values())
        assert "openai" in MODEL_VENDOR_MAP.values() or any("gpt" in v for v in MODEL_VENDOR_MAP.values())
        assert "google" in MODEL_VENDOR_MAP.values() or any("gemini" in v for v in MODEL_VENDOR_MAP.values())

    def test_vendor_detection(self):
        """测试厂商检测功能"""
        assignment = ModelAssignment(model_id="claude-sonnet-4")
        assert assignment.vendor == "anthropic"

        assignment2 = ModelAssignment(model_id="gpt-4o")
        assert assignment2.vendor == "openai"

        assignment3 = ModelAssignment(model_id="gemini-2-5-pro")
        assert assignment3.vendor == "google"


class TestCreateCrossModelDebater:
    """测试便捷工厂函数"""

    def test_create_with_role_map(self, mock_gateway):
        """测试通过角色映射创建"""
        debater = create_cross_model_debater(
            mock_gateway,
            module_name="idea_debate",
            role_model_map={
                "innovator": ["claude"],
                "skeptic": ["gpt4o"],
                "synthesizer": ["gemini"],
            }
        )
        assert debater is not None
        assert isinstance(debater, CrossModelDebater)

    def test_create_with_defaults(self, mock_gateway):
        """测试使用默认配置创建"""
        debater = create_cross_model_debater(mock_gateway)
        assert debater is not None
