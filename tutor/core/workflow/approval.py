"""审批步骤与审批管理器

支持在工作流中插入人工审批节点，工作流在审批点暂停，
等待用户通过API批准或拒绝后继续。

使用方式：
    from core.workflow.approval import ApprovalStep, ApprovalManager, ApprovalStatus

    # 在工作流中使用
    steps = [
        SomeStep(),
        ApprovalStep(approval_id="review_gate", title="Review results before proceeding"),
        FinalStep(),
    ]

    # 在API中使用
    manager = ApprovalManager()
    result = await manager.wait_for_approval(approval_id, timeout=3600)
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from tutor.core.workflow.base import WorkflowStep

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """审批状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ApprovalRequest:
    """单个审批请求"""

    def __init__(
        self,
        approval_id: str,
        run_id: str,
        title: str,
        description: str = "",
        context_data: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 3600,
    ):
        self.approval_id = approval_id
        self.run_id = run_id
        self.title = title
        self.description = description
        self.context_data = context_data or {}
        self.timeout_seconds = timeout_seconds
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.now(timezone.utc)
        self.resolved_at: Optional[datetime] = None
        self.resolved_by: Optional[str] = None
        self.comment: Optional[str] = None
        self._event: asyncio.Event = asyncio.Event()

    def approve(self, by: str = "user", comment: str = "") -> None:
        """批准"""
        self.status = ApprovalStatus.APPROVED
        self.resolved_at = datetime.now(timezone.utc)
        self.resolved_by = by
        self.comment = comment
        self._event.set()
        logger.info(f"Approval {self.approval_id} APPROVED by {by}")

    def reject(self, by: str = "user", comment: str = "") -> None:
        """拒绝"""
        self.status = ApprovalStatus.REJECTED
        self.resolved_at = datetime.now(timezone.utc)
        self.resolved_by = by
        self.comment = comment
        self._event.set()
        logger.info(f"Approval {self.approval_id} REJECTED by {by}: {comment}")

    def cancel(self) -> None:
        """取消（如工作流被终止）"""
        self.status = ApprovalStatus.CANCELLED
        self.resolved_at = datetime.now(timezone.utc)
        self._event.set()

    async def wait(self, timeout: Optional[int] = None) -> ApprovalStatus:
        """等待审批结果

        Args:
            timeout: 超时秒数，None表示使用请求默认超时

        Returns:
            最终审批状态
        """
        timeout_secs = timeout if timeout is not None else self.timeout_seconds
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout_secs)
        except asyncio.TimeoutError:
            self.status = ApprovalStatus.TIMEOUT
            self.resolved_at = datetime.now(timezone.utc)
            logger.warning(f"Approval {self.approval_id} timed out after {timeout_secs}s")
        return self.status

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（API响应用）"""
        return {
            "approval_id": self.approval_id,
            "run_id": self.run_id,
            "title": self.title,
            "description": self.description,
            "context_data": self.context_data,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() + "Z" if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "comment": self.comment,
            "timeout_seconds": self.timeout_seconds,
        }


class ApprovalManager:
    """审批管理器

    管理所有待审批请求。在工作流步骤和API层之间桥接。

    使用方式：
        manager = ApprovalManager()

        # 工作流层：创建并等待审批
        request = manager.create_request(...)
        status = await request.wait()

        # API层：查询和审批
        pending = manager.list_pending()
        manager.approve(approval_id, by="admin", comment="LGTM")
    """

    def __init__(self, storage_path: str = None):
        import os
        from pathlib import Path
        self._requests: Dict[str, ApprovalRequest] = {}
        # Use path relative to current working directory
        if storage_path is None:
            storage_path = "test_results/approvals.json"
        self._storage_path = str(Path(storage_path).resolve())
        self._load_from_file()

    def _load_from_file(self):
        """从文件加载审批请求"""
        import json
        import os
        if os.path.exists(self._storage_path):
            try:
                with open(self._storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for approval_data in data.values():
                    request = ApprovalRequest(
                        approval_id=approval_data['approval_id'],
                        run_id=approval_data['run_id'],
                        title=approval_data['title'],
                        description=approval_data.get('description', ''),
                        context_data=approval_data.get('context_data'),
                        timeout_seconds=approval_data.get('timeout_seconds', 3600),
                    )
                    # 恢复状态
                    status = approval_data.get('status', 'pending')
                    if status == 'approved':
                        request.approve(by=approval_data.get('resolved_by', 'system'), comment=approval_data.get('comment', ''))
                    elif status == 'rejected':
                        request.reject(by=approval_data.get('resolved_by', 'system'), comment=approval_data.get('comment', ''))
                    elif status == 'cancelled':
                        request.cancel()
                    self._requests[request.approval_id] = request
            except Exception as e:
                logger.warning(f"Failed to load approvals from file: {e}")

    def _save_to_file(self):
        """保存审批请求到文件"""
        import json
        import os
        os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
        data = {}
        for approval_id, request in self._requests.items():
            data[approval_id] = {
                'approval_id': request.approval_id,
                'run_id': request.run_id,
                'title': request.title,
                'description': request.description,
                'status': request.status.value,
                'context_data': request.context_data,
                'timeout_seconds': request.timeout_seconds,
                'created_at': str(request.created_at),
                'resolved_by': request.resolved_by,
                'comment': request.comment,
            }
        with open(self._storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create_request(
        self,
        approval_id: str,
        run_id: str,
        title: str,
        description: str = "",
        context_data: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 3600,
    ) -> ApprovalRequest:
        """创建审批请求"""
        request = ApprovalRequest(
            approval_id=approval_id,
            run_id=run_id,
            title=title,
            description=description,
            context_data=context_data,
            timeout_seconds=timeout_seconds,
        )
        self._requests[approval_id] = request
        self._save_to_file()
        logger.info(f"Approval request created: {approval_id}")
        return request

    def get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        """获取审批请求"""
        return self._requests.get(approval_id)

    def approve(
        self, approval_id: str, by: str = "user", comment: str = ""
    ) -> bool:
        """批准审批请求"""
        request = self._requests.get(approval_id)
        if not request:
            return False
        if request.status != ApprovalStatus.PENDING:
            return False
        request.approve(by=by, comment=comment)
        self._save_to_file()
        return True

    def reject(
        self, approval_id: str, by: str = "user", comment: str = ""
    ) -> bool:
        """拒绝审批请求"""
        request = self._requests.get(approval_id)
        if not request:
            return False
        if request.status != ApprovalStatus.PENDING:
            return False
        request.reject(by=by, comment=comment)
        self._save_to_file()
        return True

    def cancel(self, approval_id: str) -> bool:
        """取消审批请求"""
        request = self._requests.get(approval_id)
        if not request:
            return False
        request.cancel()
        self._save_to_file()
        return True

    def list_pending(self, run_id: Optional[str] = None) -> List[ApprovalRequest]:
        """列出待审批请求"""
        result = [
            r for r in self._requests.values()
            if r.status == ApprovalStatus.PENDING
        ]
        if run_id:
            result = [r for r in result if r.run_id == run_id]
        return result

    def list_all(
        self, run_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[ApprovalRequest]:
        """列出所有审批请求"""
        result = list(self._requests.values())
        if run_id:
            result = [r for r in result if r.run_id == run_id]
        if status:
            result = [r for r in result if r.status.value == status]
        return result

    def cleanup(self, older_than_seconds: int = 86400) -> int:
        """清理已解决的旧审批请求"""
        now = datetime.now(timezone.utc)
        to_remove = []
        for aid, req in self._requests.items():
            if (
                req.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED,
                               ApprovalStatus.TIMEOUT, ApprovalStatus.CANCELLED)
                and req.resolved_at
                and (now - req.resolved_at).total_seconds() > older_than_seconds
            ):
                to_remove.append(aid)
        for aid in to_remove:
            del self._requests[aid]
        return len(to_remove)


# Global approval manager singleton
approval_manager = ApprovalManager()


class ApprovalStep(WorkflowStep):
    """审批工作流步骤

    在工作流中插入此步骤，工作流将暂停并等待人工审批。

    配置示例：
    ```yaml
    workflow:
      review:
        approval:
          enabled: true
          timeout: 3600  # 1小时超时
    ```

    如果审批被拒绝或超时，步骤会抛出WorkflowError。
    """

    def __init__(self, title: str = "Approval Required", description: str = "",
                 timeout_seconds: int = 3600):
        # 组合完整描述传给父类
        full_description = f"{title}: {description}" if description else title
        super().__init__(
            name="approval_gate",
            description=full_description
        )
        self.title = title
        self._description = description
        self.timeout_seconds = timeout_seconds

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        """执行审批步骤（同步包装异步等待）"""
        run_id = context.workflow_id
        approval_id = f"{run_id}_{self.name}"

        # 获取或创建审批请求
        request = approval_manager.get_request(approval_id)
        if not request:
            request = approval_manager.create_request(
                approval_id=approval_id,
                run_id=run_id,
                title=self.title,
                description=self.description,
                context_data=self._extract_context(context),
                timeout_seconds=self.timeout_seconds,
            )

        logger.info(f"Waiting for approval: {approval_id}")

        # 同步等待（在asyncio事件循环中运行）
        try:
            loop = asyncio.get_event_loop()
            status = loop.run_until_complete(request.wait())
        except RuntimeError:
            # 没有运行中的事件循环，创建一个
            status = asyncio.run(request.wait())

        if status == ApprovalStatus.APPROVED:
            logger.info(f"Approval granted: {approval_id}")
            return {
                "approved": True,
                "approval_id": approval_id,
                "approved_by": request.resolved_by,
                "comment": request.comment,
            }
        else:
            logger.warning(f"Approval not granted: {approval_id} (status={status.value})")
            return {
                "approved": False,
                "approval_id": approval_id,
                "status": status.value,
                "reason": request.comment or f"Approval {status.value}",
            }

    def _extract_context(self, context: "WorkflowContext") -> Dict[str, Any]:
        """提取上下文信息供审批界面展示"""
        data = {"workflow_id": context.workflow_id}
        # 提取关键状态摘要
        for key in ["outline", "experiment_summary", "draft_sections", "review_results"]:
            val = context.get_state(key)
            if val:
                if isinstance(val, dict):
                    data[key] = {k: str(v)[:200] for k, v in val.items()}
                else:
                    data[key] = str(val)[:500]
        return data

    def validate(self, context: "WorkflowContext") -> List[str]:
        # 审批步骤始终有效
        return []


__all__ = [
    "ApprovalStep",
    "ApprovalManager",
    "ApprovalStatus",
    "ApprovalRequest",
    "approval_manager",
]
