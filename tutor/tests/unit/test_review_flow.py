import pytest
from unittest.mock import MagicMock, patch
from tutor.core.workflow.review import PaperReviewStep, ReviewFlow
from tutor.core.model import ModelGateway

class MockWorkflowContext:
    def __init__(self, steps_list=None):
        self.steps = steps_list or []
        self.state = {}
        self.config = {"steps": len(self.steps)}
        self.workflow_id = "test_review"
        self.workflow_type = "review"
        self.results_dir = MagicMock()
        
    def get_state(self, key, default=None):
        return self.state.get(key, default)
        
    def set_state(self, key, value):
        self.state[key] = value
        
    def update_state(self, data):
        self.state.update(data)

@pytest.fixture
def mock_context():
    return MockWorkflowContext()

@pytest.fixture
def mock_model_gateway():
    return MagicMock(spec=ModelGateway)

class TestPaperReviewStep:
    def test_step_initialization(self, mock_model_gateway):
        step = PaperReviewStep(mock_model_gateway)
        assert step.name == "paper_review"
        assert "mode: single" in step.description

    def test_validate_missing_content(self, mock_model_gateway, mock_context):
        step = PaperReviewStep(mock_model_gateway)
        errors = step.validate(mock_context)
        assert "No paper_content found" in errors[0]

    def test_validate_with_content(self, mock_model_gateway, mock_context):
        mock_context.set_state("paper_content", {"title": "Test Paper"})
        step = PaperReviewStep(mock_model_gateway)
        errors = step.validate(mock_context)
        assert len(errors) == 0

    def test_execute_success(self, mock_model_gateway, mock_context):
        # Mock LLM Response
        mock_model_gateway.chat.return_value = """
# Academic Review Report

**Originality**: 8/10
**Methodological Rigor**: 7/10
**Experimental Completeness**: 9/10
**Writing Quality**: 8/10
**Significance**: 7/10

Overall Recommendation: Minor Revisions
Key Contribution: Novel approach to super-resolution using equivariant filters.
        """
        
        mock_context.set_state("paper_content", {
            "title": "Equivariant SR",
            "abstract": "Test abstract",
            "introduction": "Test intro",
            "methodology": "Test method",
            "experiments": "Test exp",
            "conclusion": "Test conclusion"
        })
        
        step = PaperReviewStep(mock_model_gateway)
        result = step.execute(mock_context)
        
        assert result["overall_score"] >= 0.7  # (8+7+9+8+7)/50 = 0.78
        assert result["recommendation"] == "Minor Revisions"
        assert "equivariant filters" in result["key_contribution"]
        assert result["reviewer"] == "single-role-mvp"

    def test_execute_failure(self, mock_model_gateway, mock_context):
        mock_model_gateway.chat.side_effect = Exception("API Error")
        mock_context.set_state("paper_content", {"title": "Test Paper"})
        
        step = PaperReviewStep(mock_model_gateway)
        with pytest.raises(Exception):
            step.execute(mock_context)

    def test_parse_review_various_formats(self, mock_model_gateway):
        step = PaperReviewStep(mock_model_gateway)

        # Test Format 1: Dim: Score
        review1 = "Originality: 9. Significance: 8"
        scores1, rec1, _ = step._parse_review_text(review1)
        assert scores1["originality"] == 0.9
        assert scores1["significance"] == 0.8

        # Test Format 2: Dim (Score/10)
        review2 = "Methodological Rigor (7/10). Writing Quality (8/10)"
        scores2, rec2, _ = step._parse_review_text(review2)
        assert scores2["methodological_rigor"] == 0.7
        assert scores2["writing_quality"] == 0.8

        # Test Format 3: Decision
        review3 = "Recommendation: Major Revisions"
        _, rec3, _ = step._parse_review_text(review3)
        assert rec3 == "Major Revisions"

class TestReviewFlow:
    def test_build_steps(self, mock_model_gateway):
        flow = ReviewFlow(
            workflow_id="test_flow",
            config={},
            storage_path=MagicMock(),
            model_gateway=mock_model_gateway
        )
        steps = flow.build_steps()
        assert len(steps) == 1
        assert isinstance(steps[0], PaperReviewStep)
