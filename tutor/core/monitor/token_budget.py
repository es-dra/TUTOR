"""TUTOR Token Budget - Token 预算管理

跟踪工作流的 Token 消耗，在接近预算上限时发出警告。

设计文档建议:
- 会话级别 Token 预算上限
- 在超过 80% 时发出预警
- 在超过 95% 时考虑暂停工作流
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class TokenBudgetWarning:
    """Token 预算警告"""
    budget_type: str  # "session", "step"
    current_tokens: int
    budget_tokens: int
    usage_percent: float
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_type": self.budget_type,
            "current_tokens": self.current_tokens,
            "budget_tokens": self.budget_tokens,
            "usage_percent": self.usage_percent,
            "message": self.message,
        }


class TokenBudget:
    """Token 预算管理器

    跟踪工作流的 Token 消耗，支持:
    - 会话级别预算设置
    - 步骤级别预算设置
    - 80% 预警阈值
    - 95% 暂停阈值
    """

    DEFAULT_SESSION_BUDGET = 100000  # 默认 100K tokens
    WARNING_THRESHOLD = 0.80  # 80%
    PAUSE_THRESHOLD = 0.95  # 95%

    def __init__(
        self,
        session_budget: Optional[int] = None,
        on_warning: Optional[Callable[[TokenBudgetWarning], None]] = None,
    ):
        """初始化 Token 预算管理器

        Args:
            session_budget: 会话总预算（tokens），None 则使用默认值
            on_warning: 警告回调函数
        """
        self.session_budget = session_budget or self.DEFAULT_SESSION_BUDGET
        self.on_warning = on_warning

        # 跟踪
        self._current_tokens = 0
        self._step_costs: Dict[str, int] = {}
        self._warning_issued = False

    @property
    def current_tokens(self) -> int:
        """当前已用 tokens"""
        return self._current_tokens

    @property
    def budget_tokens(self) -> int:
        """预算 tokens"""
        return self.session_budget

    @property
    def usage_percent(self) -> float:
        """使用百分比"""
        return self._current_tokens / self.session_budget if self.session_budget > 0 else 0

    def add_cost(self, tokens: int, step_name: str = "unknown") -> None:
        """添加 Token 消耗

        Args:
            tokens: 消耗的 tokens 数量
            step_name: 步骤名称（用于追踪）
        """
        self._current_tokens += tokens
        self._step_costs[step_name] = self._step_costs.get(step_name, 0) + tokens

        logger.debug(f"Token cost added: {tokens} for '{step_name}'. Total: {self._current_tokens}/{self.session_budget}")

        # 检查是否需要发出警告
        self._check_warnings()

    def _check_warnings(self) -> None:
        """检查是否需要发出警告"""
        usage = self.usage_percent

        if usage >= self.PAUSE_THRESHOLD and not self._warning_issued:
            # 严重警告 - 接近预算上限
            warning = TokenBudgetWarning(
                budget_type="session",
                current_tokens=self._current_tokens,
                budget_tokens=self.session_budget,
                usage_percent=usage,
                message=f"Token usage at {usage*100:.1f}%, budget nearly exhausted! Consider pausing workflow.",
            )
            logger.warning(warning.message)
            self._warning_issued = True

            if self.on_warning:
                self.on_warning(warning)

        elif usage >= self.WARNING_THRESHOLD and not self._warning_issued:
            # 正常警告
            warning = TokenBudgetWarning(
                budget_type="session",
                current_tokens=self._current_tokens,
                budget_tokens=self.session_budget,
                usage_percent=usage,
                message=f"Token usage at {usage*100:.1f}% of budget. Consider optimizing.",
            )
            logger.info(warning.message)

            if self.on_warning:
                self.on_warning(warning)
                self._warning_issued = True

    def can_proceed(self, estimated_tokens: int = 0) -> bool:
        """检查是否可以继续执行

        Args:
            estimated_tokens: 预估需要消耗的 tokens

        Returns:
            True 如果可以继续，False 如果预算不足
        """
        projected = self._current_tokens + estimated_tokens
        return projected <= self.session_budget

    def check_step(self, step_name: str, estimated_tokens: int) -> TokenBudgetWarning:
        """检查步骤是否可以执行

        Args:
            step_name: 步骤名称
            estimated_tokens: 预估 tokens

        Returns:
            TokenBudgetWarning 如果即将超预算，None 如果正常
        """
        projected = self._current_tokens + estimated_tokens
        projected_percent = projected / self.session_budget if self.session_budget > 0 else 0

        if projected_percent >= self.PAUSE_THRESHOLD:
            warning = TokenBudgetWarning(
                budget_type="step",
                current_tokens=projected,
                budget_tokens=self.session_budget,
                usage_percent=projected_percent,
                message=f"Step '{step_name}' may exceed budget. Projected: {projected_tokens} tokens ({projected_percent*100:.1f}%)",
            )
            logger.warning(warning.message)
            return warning

        elif projected_percent >= self.WARNING_THRESHOLD:
            warning = TokenBudgetWarning(
                budget_type="step",
                current_tokens=projected,
                budget_tokens=self.session_budget,
                usage_percent=projected_percent,
                message=f"Step '{step_name}' will use significant budget. Projected: {projected_tokens} tokens ({projected_percent*100:.1f}%)",
            )
            logger.info(warning.message)
            return warning

        return None

    def get_summary(self) -> Dict[str, Any]:
        """获取预算摘要"""
        return {
            "current_tokens": self._current_tokens,
            "budget_tokens": self.session_budget,
            "usage_percent": self.usage_percent,
            "remaining_tokens": self.session_budget - self._current_tokens,
            "step_costs": self._step_costs.copy(),
        }

    def reset(self) -> None:
        """重置预算计数器"""
        self._current_tokens = 0
        self._step_costs.clear()
        self._warning_issued = False


class WorkflowTokenTracker:
    """工作流 Token 追踪器

    集成到 WorkflowContext 中，跟踪整个工作流的 Token 消耗。
    """

    def __init__(self, budget: Optional[TokenBudget] = None):
        self.budget = budget or TokenBudget()
        self.enabled = True

    def estimate_prompt_tokens(self, messages: list, max_tokens: int) -> int:
        """估算提示的 tokens 数量

        使用粗略估算: 平均每个字符约 0.25 tokens

        Args:
            messages: 消息列表
            max_tokens: 最大生成 tokens

        Returns:
            估算的 total tokens
        """
        # 估算输入 tokens
        input_chars = sum(len(m.get("content", "")) for m in messages)
        input_tokens = int(input_chars * 0.25)

        # 总计
        return input_tokens + max_tokens

    def record_api_call(self, messages: list, max_tokens: int, step_name: str) -> None:
        """记录一次 API 调用

        Args:
            messages: 消息列表
            max_tokens: 请求的 max_tokens
            step_name: 步骤名称
        """
        if not self.enabled:
            return

        estimated = self.estimate_prompt_tokens(messages, max_tokens)
        self.budget.add_cost(estimated, step_name)

    def get_budget(self) -> TokenBudget:
        """获取预算管理器"""
        return self.budget
