"""TUTOR Review Module - 自动评审循环框架

核心组件:
- AutoReviewer: 自动评审循环
- CrossModelReviewer: 跨模型对抗评审
- ScoreAggregator: 评分聚合器
"""

from .auto_reviewer import (
    AutoReviewer,
    ReviewResult,
    ReviewIteration,
    ReviewConfig,
    get_default_review_config,
)
from .cross_model_reviewer import (
    CrossModelReviewer,
    ReviewRole,
    ModelReviewResponse,
    ReviewVerdict,
)

__all__ = [
    # Auto Review
    "AutoReviewer",
    "ReviewResult",
    "ReviewIteration",
    "ReviewConfig",
    "get_default_review_config",
    # Cross Model Review
    "CrossModelReviewer",
    "ReviewRole",
    "ModelReviewResponse",
    "ReviewVerdict",
]