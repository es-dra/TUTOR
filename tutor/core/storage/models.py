"""SQLAlchemy ORM models for workflow storage.

Models:
- WorkflowRun: Represents a single workflow execution
- RunEvent: Represents events emitted during workflow execution
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Integer,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column

Base = declarative_base()


class WorkflowRun(Base):
    """Workflow run record.

    Represents a single execution of a workflow (idea, experiment, review, write).
    Stores configuration, parameters, status, results, and metadata.
    """

    __tablename__ = "workflow_runs"

    # Primary key
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Basic info
    workflow_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    # Parameters and config (JSON stored as text)
    params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Results
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    tags: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    events: Mapped[List["RunEvent"]] = relationship(
        "RunEvent",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunEvent.created_at",
    )

    # Indexes
    __table_args__ = (
        Index("idx_runs_status", "status"),
        Index("idx_runs_type", "workflow_type"),
    )


class RunEvent(Base):
    """Event emitted during workflow execution.

    Stores a historical record of events (started, step_completed, etc.)
    for a workflow run.
    """

    __tablename__ = "run_events"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to WorkflowRun
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workflow_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Event data
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationship back to WorkflowRun
    run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="events")

    # Indexes
    __table_args__ = (
        Index("idx_events_run", "run_id"),
    )
