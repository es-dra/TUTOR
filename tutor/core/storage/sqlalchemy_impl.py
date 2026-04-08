"""SQLAlchemy implementation of WorkflowRunRepository.

This implementation uses SQLAlchemy ORM for database operations,
providing better abstraction and portability compared to raw SQL.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from tutor.core.storage.models import Base, WorkflowRun as SQLWorkflowRun, RunEvent as SQLRunEvent
from tutor.core.storage.repository import WorkflowRunRepository

logger = logging.getLogger(__name__)


class SQLAlchemyWorkflowRunRepository(WorkflowRunRepository):
    """SQLAlchemy-based implementation of workflow run storage.

    Uses SQLite by default but can work with any SQLAlchemy-supported database.
    Thread-safe via session-per-request pattern.
    """

    def __init__(self, db_url: str = "sqlite:///data/tutor_runs.db"):
        """Initialize repository with database URL.

        Args:
            db_url: SQLAlchemy database URL.
                    Use "sqlite:///:memory:" for in-memory testing.
        """
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)

    def _get_session(self) -> Session:
        """Get a new database session.

        Note: Caller is responsible for closing the session.
        """
        return self.SessionLocal()

    def _to_dict(self, run: SQLWorkflowRun) -> Dict[str, Any]:
        """Convert SQLAlchemy model to dictionary."""
        return {
            "run_id": run.run_id,
            "workflow_type": run.workflow_type,
            "status": run.status,
            "params": json.loads(run.params) if run.params else {},
            "config": json.loads(run.config) if run.config else {},
            "started_at": run.started_at.isoformat() + "Z" if run.started_at else None,
            "completed_at": run.completed_at.isoformat() + "Z" if run.completed_at else None,
            "result": json.loads(run.result) if run.result else None,
            "error": run.error,
            "usage": json.loads(run.usage) if run.usage else None,
            "tags": json.loads(run.tags) if run.tags else [],
            "created_at": run.created_at.isoformat() + "Z" if run.created_at else None,
            "updated_at": run.updated_at.isoformat() + "Z" if run.updated_at else None,
        }

    def create_run(
        self,
        run_id: str,
        workflow_type: str,
        params: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new workflow run record."""
        session = self._get_session()
        try:
            now = datetime.now(timezone.utc)
            run = SQLWorkflowRun(
                run_id=run_id,
                workflow_type=workflow_type,
                status="pending",
                params=json.dumps(params, ensure_ascii=False) if params else None,
                config=json.dumps(config, ensure_ascii=False) if config else None,
                tags="[]",
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.commit()
            return self._to_dict(run)
        finally:
            session.close()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a workflow run by ID."""
        session = self._get_session()
        try:
            run = session.query(SQLWorkflowRun).filter_by(run_id=run_id).first()
            return self._to_dict(run) if run else None
        finally:
            session.close()

    def update_status(
        self,
        run_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update the status of a workflow run."""
        session = self._get_session()
        try:
            run = session.query(SQLWorkflowRun).filter_by(run_id=run_id).first()
            if not run:
                return False

            run.status = status
            run.updated_at = datetime.now(timezone.utc)

            # Set completed_at for terminal states
            if status in ["running", "completed", "failed", "cancelled"]:
                run.completed_at = datetime.now(timezone.utc)

            if result is not None:
                run.result = json.dumps(result, ensure_ascii=False)
            if error is not None:
                run.error = error
            if usage is not None:
                run.usage = json.dumps(usage, ensure_ascii=False)

            session.commit()
            return True
        finally:
            session.close()

    def list_runs(
        self,
        status: Optional[str] = None,
        workflow_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List workflow runs with optional filtering."""
        session = self._get_session()
        try:
            query = session.query(SQLWorkflowRun)

            if status:
                query = query.filter(SQLWorkflowRun.status == status)
            if workflow_type:
                query = query.filter(SQLWorkflowRun.workflow_type == workflow_type)

            total = query.count()
            runs = query.order_by(SQLWorkflowRun.created_at.desc()).offset(offset).limit(limit).all()

            return {
                "total": total,
                "runs": [self._to_dict(run) for run in runs],
            }
        finally:
            session.close()

    def delete_run(self, run_id: str) -> bool:
        """Delete a workflow run."""
        session = self._get_session()
        try:
            run = session.query(SQLWorkflowRun).filter_by(run_id=run_id).first()
            if not run:
                return False
            session.delete(run)
            session.commit()
            return True
        finally:
            session.close()

    def update_tags(self, run_id: str, tags: List[str]) -> bool:
        """Update tags for a workflow run."""
        session = self._get_session()
        try:
            run = session.query(SQLWorkflowRun).filter_by(run_id=run_id).first()
            if not run:
                return False
            run.tags = json.dumps(tags, ensure_ascii=False)
            run.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True
        finally:
            session.close()

    def list_runs_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List workflow runs by tags."""
        session = self._get_session()
        try:
            # Build LIKE conditions for each tag
            conditions = [SQLWorkflowRun.tags.like(f'%"{tag}"%') for tag in tags]

            if match_all:
                query = session.query(SQLWorkflowRun).filter(*conditions)
            else:
                query = session.query(SQLWorkflowRun).filter(*conditions)

            runs = query.order_by(SQLWorkflowRun.created_at.desc()).offset(offset).limit(limit).all()
            return [self._to_dict(run) for run in runs]
        finally:
            session.close()

    def add_event(
        self,
        run_id: str,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add an event to a workflow run's history."""
        session = self._get_session()
        try:
            event = SQLRunEvent(
                run_id=run_id,
                event_type=event_type,
                event_data=json.dumps(event_data, ensure_ascii=False) if event_data else None,
                created_at=datetime.now(timezone.utc),
            )
            session.add(event)
            session.commit()
        finally:
            session.close()

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all events for a workflow run."""
        session = self._get_session()
        try:
            events = (
                session.query(SQLRunEvent)
                .filter_by(run_id=run_id)
                .order_by(SQLRunEvent.created_at.asc())
                .all()
            )
            return [
                {
                    "id": e.id,
                    "run_id": e.run_id,
                    "event_type": e.event_type,
                    "event_data": json.loads(e.event_data) if e.event_data else None,
                    "created_at": e.created_at.isoformat() + "Z" if e.created_at else None,
                }
                for e in events
            ]
        finally:
            session.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get workflow run statistics."""
        session = self._get_session()
        try:
            total = session.query(SQLWorkflowRun).count()

            by_status = {}
            for row in session.query(SQLWorkflowRun.status, func.count()).group_by(SQLWorkflowRun.status).all():
                by_status[row[0]] = row[1]

            by_type = {}
            for row in session.query(SQLWorkflowRun.workflow_type, func.count()).group_by(SQLWorkflowRun.workflow_type).all():
                by_type[row[0]] = row[1]

            return {
                "total": total,
                "by_status": by_status,
                "by_type": by_type,
            }
        finally:
            session.close()
