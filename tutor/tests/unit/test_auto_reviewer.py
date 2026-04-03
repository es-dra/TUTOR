"""Tests for AutoReviewer and CrossModelReviewer - 自动评审框架测试"""

import pytest
from unittest.mock import MagicMock
from tutor.core.review.auto_reviewer import (
    AutoReviewer,
    ReviewConfig,
    get_default_review_config,
)
from tutor.core.review.cross_model_reviewer import (
    CrossModelReviewer,
    ReviewRole,
    ReviewVerdict,
)


class MockModelGateway:
    """Mock ModelGateway for testing"""

    def __init__(self):
        self.call_count = 0
        self.calls = []

    def chat(self, model_name, messages, temperature=0.7, max_tokens=2000):
        self.call_count += 1
        self.calls.append({
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        })
        return f"Review response {self.call_count} about the research paper. The methodology is sound but could be improved."

    def list_models(self):
        return ["gpt-4o", "claude-sonnet-4"]


@pytest.fixture
def mock_gateway():
    return MockModelGateway()


@pytest.fixture
def default_review_config():
    return get_default_review_config()


class TestReviewConfig:
    """测试ReviewConfig配置"""

    def test_default_config(self):
        config = get_default_review_config()
        assert config.max_iterations == 3
        assert config.score_threshold == 0.7
        assert len(config.models) >= 1
        assert config.parallel_reviews is True
        assert config.improvement_strength == 0.8

    def test_custom_config(self):
        config = ReviewConfig(
            max_iterations=5,
            score_threshold=0.8,
            models=["gpt-4o", "claude-sonnet-4"],
            parallel_reviews=False,
        )
        assert config.max_iterations == 5
        assert config.score_threshold == 0.8
        assert config.parallel_reviews is False


class TestAutoReviewer:
    """测试AutoReviewer"""

    def test_reviewer_initialization(self, mock_gateway, default_review_config):
        reviewer = AutoReviewer(mock_gateway, default_review_config)
        assert reviewer.config.max_iterations == 3
        # Note: gateway is wrapped in an adapter

    def test_review_sync_runs(self, mock_gateway, default_review_config):
        reviewer = AutoReviewer(mock_gateway, default_review_config)
        result = reviewer.review_sync(
            content="This is a research paper about machine learning.",
            context="Additional context about the research.",
        )
        assert result is not None
        assert hasattr(result, "initial_score")
        assert hasattr(result, "final_score")

    def test_review_score_improvement(self, mock_gateway):
        config = ReviewConfig(
            max_iterations=2,
            score_threshold=0.9,  # High threshold so it won't converge
            models=["gpt-4o"],
            parallel_reviews=False,
            improvement_strength=0.5,
        )
        reviewer = AutoReviewer(mock_gateway, config)
        result = reviewer.review_sync(content="Test research paper content.")

        assert result is not None
        assert result.total_iterations <= 2

    def test_review_iteration_count(self, mock_gateway):
        config = ReviewConfig(
            max_iterations=2,
            score_threshold=0.95,  # Won't converge
            models=["gpt-4o"],
            parallel_reviews=False,
        )
        reviewer = AutoReviewer(mock_gateway, config)
        result = reviewer.review_sync(content="Test paper", context="")

        assert result.total_iterations <= 2

    def test_convergence_detection(self, mock_gateway):
        """测试收敛检测"""
        config = ReviewConfig(
            max_iterations=10,
            score_threshold=0.7,
            models=["gpt-4o"],
            parallel_reviews=False,
        )
        reviewer = AutoReviewer(mock_gateway, config)
        result = reviewer.review_sync(content="A well-written machine learning paper.")

        # Should either converge or reach max iterations
        assert result.total_iterations > 0
        assert result.final_score >= 0


class TestAutoReviewerPrivateMethods:
    """测试AutoReviewer私有方法"""

    def test_aggregate_scores(self, mock_gateway, default_review_config):
        reviewer = AutoReviewer(mock_gateway, default_review_config)

        # Create mock reviews with proper dimension attributes
        review1 = MagicMock()
        review1.innovation = 0.8
        review1.feasibility = 0.7
        review1.methodology = 0.8
        review1.impact = 0.7
        review1.clarity = 0.7

        review2 = MagicMock()
        review2.innovation = 0.9
        review2.feasibility = 0.8
        review2.methodology = 0.9
        review2.impact = 0.8
        review2.clarity = 0.8

        reviews = [review1, review2]

        result = reviewer._aggregate_scores(reviews)
        # Returns tuple (score, scores_dict)
        assert isinstance(result, tuple)
        score, scores = result
        # Score should be weighted average
        assert 0.0 <= score <= 1.0
        assert "innovation" in scores

    def test_aggregate_scores_empty(self, mock_gateway, default_review_config):
        reviewer = AutoReviewer(mock_gateway, default_review_config)
        score, _ = reviewer._aggregate_scores([])
        assert score == 0.0


class TestCrossModelReviewer:
    """测试CrossModelReviewer"""

    def test_reviewer_initialization(self, mock_gateway):
        reviewer = CrossModelReviewer(
            model_gateway=mock_gateway,
            primary_model="gpt-4o",
            critic_model="claude-sonnet-4",
            synthesizer_model="gemini-2-5-pro",
        )
        assert reviewer.primary_model == "gpt-4o"
        assert reviewer.critic_model == "claude-sonnet-4"
        assert reviewer.synthesizer_model == "gemini-2-5-pro"

    def test_review_sync_returns_result(self, mock_gateway):
        reviewer = CrossModelReviewer(
            model_gateway=mock_gateway,
            primary_model="gpt-4o",
            critic_model="claude-sonnet-4",
            synthesizer_model="gpt-4o",
        )
        result = reviewer.review_sync(
            content="Research paper about deep learning.",
            context="Machine learning context.",
        )

        assert result is not None
        assert hasattr(result, "advocate_response")
        assert hasattr(result, "critic_response")
        assert hasattr(result, "synthesis_response")
        assert hasattr(result, "final_score")


class TestReviewRole:
    """测试ReviewRole枚举"""

    def test_review_roles_exist(self):
        assert ReviewRole.ADVOCATE is not None
        assert ReviewRole.CRITIC is not None
        assert ReviewRole.SYNTHESIZER is not None

    def test_review_role_values(self):
        assert ReviewRole.ADVOCATE.value == "advocate"
        assert ReviewRole.CRITIC.value == "critic"
        assert ReviewRole.SYNTHESIZER.value == "synthesizer"


class TestReviewVerdict:
    """测试ReviewVerdict"""

    def test_verdict_requires_score(self):
        # ReviewVerdict requires score as positional argument
        with pytest.raises(TypeError):
            ReviewVerdict(final_verdict="Accept")
