import pytest
from unittest.mock import MagicMock, patch
from tutor.core.workflow.write import OutlineGenerationStep, WriteFlow
from tutor.core.model import ModelGateway

class MockWorkflowContext:
    def __init__(self, steps_list=None):
        self.steps = steps_list or []
        self.state = {}
        self.config = {"output_format": "markdown", "steps": len(self.steps)}
        self.workflow_id = "test_write"
        self.workflow_type = "write"
        self.results_dir = MagicMock()
        
    def get_state(self, key, default=None):
        return self.state.get(key, default)
        
    def set_state(self, key, value):
        self.state[key] = value
        
    def update_state(self, data):
        self.state.update(data)

    def get_all_state(self):
        return self.state.copy()

@pytest.fixture
def mock_context():
    return MockWorkflowContext()

@pytest.fixture
def mock_model_gateway():
    return MagicMock(spec=ModelGateway)

class TestOutlineGenerationStep:
    def test_step_initialization(self, mock_model_gateway):
        step = OutlineGenerationStep(mock_model_gateway)
        assert step.name == "outline_generation"

    def test_execute_success(self, mock_model_gateway, mock_context):
        # Mock LLM Response
        mock_model_gateway.chat.return_value = """
# Paper Outline: Equivariant Filters

## 1. Title
Equivariant Filters for Super-Resolution

## 2. Abstract
This paper proposes...

## 3. Introduction
SR is a challenging task...
"""
        
        mock_context.set_state("topic", "Equivariant Filters")
        mock_context.set_state("experiment_summary", {"title": "Exp1", "metrics": {"PSNR": 32.5}})
        
        step = OutlineGenerationStep(mock_model_gateway)
        result = step.execute(mock_context)
        
        assert "outline_text" in result
        assert len(result["sections"]) > 0
        assert "Title" in result["sections"] or "Title" in str(result["sections"])

class TestWriteFlow:
    def test_build_steps(self, mock_model_gateway):
        flow = WriteFlow(
            workflow_id="test_write_flow",
            config={},
            storage_path=MagicMock(),
            model_gateway=mock_model_gateway
        )
        steps = flow.build_steps()
        assert len(steps) >= 2
        assert any(isinstance(s, OutlineGenerationStep) for s in steps)
