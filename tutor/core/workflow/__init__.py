"""TUTOR Workflow Engine - 工作流引擎

提供统一的工作流定义、执行和状态管理。
"""

from .base import (
    WorkflowStatus,
    CheckpointData,
    WorkflowResult,
    WorkflowContext,
    WorkflowStep,
    Workflow,
    WorkflowEngine,
)
from .idea import (
    IdeaFlow,
    PaperLoadingStep,
    PaperValidationStep,
    LiteratureAnalysisStep,
    IdeaDebateStep,
    IdeaEvaluationStep,
    FinalProposalStep,
)
from .paper_parser import (
    PaperMetadata,
    PDFParser,
    ArXivParser,
    SmartPaperParser,
    PaperParseError,
    parse_paper,
    is_supported,
)

__all__ = [
    # Base
    'WorkflowStatus',
    'CheckpointData',
    'WorkflowResult',
    'WorkflowContext',
    'WorkflowStep',
    'Workflow',
    'WorkflowEngine',
    # IdeaFlow
    'IdeaFlow',
    'PaperLoadingStep',
    'PaperValidationStep',
    'LiteratureAnalysisStep',
    'IdeaDebateStep',
    'IdeaEvaluationStep',
    'FinalProposalStep',
    # Parsers
    'PaperMetadata',
    'PDFParser',
    'ArXivParser',
    'SmartPaperParser',
    'PaperParseError',
    'parse_paper',
    'is_supported',
]