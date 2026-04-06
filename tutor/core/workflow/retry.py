"""TUTOR Workflow Retry & Rollback - 工作流重试与回滚机制

提供指数退避重试、失败策略（ROLLBACK/STOP/CONTINUE）和回滚链管理。
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Type, Any, Optional

logger = logging.getLogger(__name__)


class FailureStrategy(Enum):
    """步骤失败时的处理策略"""
    ROLLBACK = "rollback"
    STOP = "stop"
    CONTINUE = "continue"
    PAUSE = "pause"


@dataclass
class RetryPolicy:
    """重试策略配置"""
    max_attempts: int = 3
    backoff: str = "exponential"  # exponential | fixed
    base_delay: float = 1.0
    max_delay: float = 60.0
    retryable_exceptions: List[Type[Exception]] = field(default_factory=lambda: [Exception])


class WorkflowRetryManager:
    """工作流重试管理器"""

    @staticmethod
    def compute_delay(policy: RetryPolicy, attempt: int) -> float:
        """计算退避延迟"""
        if policy.backoff == "exponential":
            delay = policy.base_delay * (2 ** attempt)
        else:
            delay = policy.base_delay
        return min(delay, policy.max_delay)

    def execute_with_retry(
        self,
        step: Any,
        context: Any,
        policy: RetryPolicy,
        failure_strategy: FailureStrategy = FailureStrategy.STOP,
    ) -> Dict[str, Any]:
        """带重试的步骤执行

        Args:
            step: WorkflowStep 实例
            context: WorkflowContext 实例
            policy: 重试策略
            failure_strategy: 失败处理策略

        Returns:
            步骤执行结果

        Raises:
            Exception: 重试耗尽且策略为 STOP 时抛出
        """
        last_error: Optional[Exception] = None

        for attempt in range(policy.max_attempts):
            try:
                if attempt > 0:
                    delay = self.compute_delay(policy, attempt - 1)
                    logger.info(
                        f"Retry step '{step.name}': attempt {attempt + 1}/{policy.max_attempts}, "
                        f"delay={delay:.1f}s"
                    )
                    time.sleep(delay)

                result = step.execute(context)
                if attempt > 0:
                    logger.info(f"Step '{step.name}' succeeded on attempt {attempt + 1}")
                return result

            except Exception as e:
                last_error = e
                is_retryable = any(
                    isinstance(e, exc_type) for exc_type in policy.retryable_exceptions
                )
                logger.warning(
                    f"Step '{step.name}' attempt {attempt + 1}/{policy.max_attempts} failed: {e} "
                    f"(retryable={is_retryable})"
                )

                if not is_retryable or attempt >= policy.max_attempts - 1:
                    break

        # 重试耗尽
        if failure_strategy == FailureStrategy.STOP:
            raise last_error  # type: ignore
        elif failure_strategy == FailureStrategy.CONTINUE:
            logger.warning(f"Step '{step.name}' failed, continuing (CONTINUE strategy)")
            return {}
        else:
            logger.warning(f"Step '{step.name}' failed, will rollback (ROLLBACK strategy)")
            raise last_error  # type: ignore
    
    async def execute_with_retry_async(
        self,
        step: Any,
        context: Any,
        policy: RetryPolicy,
        failure_strategy: FailureStrategy = FailureStrategy.STOP,
    ) -> Dict[str, Any]:
        """异步带重试的步骤执行

        Args:
            step: WorkflowStep 实例
            context: WorkflowContext 实例
            policy: 重试策略
            failure_strategy: 失败处理策略

        Returns:
            步骤执行结果

        Raises:
            Exception: 重试耗尽且策略为 STOP 时抛出
        """
        import asyncio
        last_error: Optional[Exception] = None

        for attempt in range(policy.max_attempts):
            try:
                if attempt > 0:
                    delay = self.compute_delay(policy, attempt - 1)
                    logger.info(
                        f"Retry step '{step.name}': attempt {attempt + 1}/{policy.max_attempts}, "
                        f"delay={delay:.1f}s"
                    )
                    await asyncio.sleep(delay)

                # 检查步骤是否有异步执行方法
                if hasattr(step, 'execute_async'):
                    result = await step.execute_async(context)
                else:
                    # 如果没有异步方法，在事件循环中执行同步方法
                    result = await asyncio.to_thread(step.execute, context)
                
                if attempt > 0:
                    logger.info(f"Step '{step.name}' succeeded on attempt {attempt + 1}")
                return result

            except Exception as e:
                last_error = e
                is_retryable = any(
                    isinstance(e, exc_type) for exc_type in policy.retryable_exceptions
                )
                logger.warning(
                    f"Step '{step.name}' attempt {attempt + 1}/{policy.max_attempts} failed: {e} "
                    f"(retryable={is_retryable})"
                )

                if not is_retryable or attempt >= policy.max_attempts - 1:
                    break

        # 重试耗尽
        if failure_strategy == FailureStrategy.STOP:
            raise last_error  # type: ignore
        elif failure_strategy == FailureStrategy.CONTINUE:
            logger.warning(f"Step '{step.name}' failed, continuing (CONTINUE strategy)")
            return {}
        else:
            logger.warning(f"Step '{step.name}' failed, will rollback (ROLLBACK strategy)")
            raise last_error  # type: ignore


class RollbackChain:
    """回滚链管理器"""

    def __init__(self) -> None:
        self._steps: List[tuple] = []

    def add_step(self, step_index: int, step: Any) -> None:
        """记录已执行的步骤"""
        self._steps.append((step_index, step))
        logger.debug(f"RollbackChain: added step {step_index} '{step.name}'")

    def rollback_all(self, context: Any) -> None:
        """逆序回滚所有已执行步骤"""
        logger.info(f"RollbackChain: rolling back {len(self._steps)} steps in reverse order")
        for step_index, step in reversed(self._steps):
            try:
                step.rollback(context)
                logger.info(f"RollbackChain: rolled back step {step_index} '{step.name}'")
            except Exception as e:
                logger.error(
                    f"RollbackChain: rollback failed for step {step_index} '{step.name}': {e}"
                )

    def clear(self) -> None:
        self._steps.clear()
