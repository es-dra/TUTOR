"""Repository Factory for workflow storage.

Provides a centralized way to get repository instances based on configuration.
Supports switching between implementations (SQLAlchemy, legacy).
"""

import logging
import os
import threading
from typing import Optional

from tutor.core.storage.repository import WorkflowRunRepository

logger = logging.getLogger(__name__)

# Module-level cache for repository instance
_impl_cache: Optional[WorkflowRunRepository] = None
_lock = threading.Lock()


def get_repository() -> WorkflowRunRepository:
    """Get the workflow run repository instance.

    Returns the cached instance if available, otherwise creates a new one
    based on the TUTOR_STORAGE_IMPL environment variable.

    Returns:
        WorkflowRunRepository: The repository instance

    Environment Variables:
        TUTOR_STORAGE_IMPL: Implementation to use.
                           Values: "sqlalchemy" (default), "legacy"
        DATABASE_URL: Database URL for SQLAlchemy. Default: sqlite:///data/tutor_runs.db
    """
    global _impl_cache

    if _impl_cache is not None:
        return _impl_cache

    with _lock:
        # Double-check after acquiring lock
        if _impl_cache is None:
            impl_type = os.environ.get("TUTOR_STORAGE_IMPL", "sqlalchemy").lower()

            if impl_type == "legacy":
                from tutor.core.storage.legacy_impl import LegacyWorkflowRunRepository
                logger.info("Using legacy SQLite repository implementation")
                _impl_cache = LegacyWorkflowRunRepository()
            else:
                from tutor.core.storage.sqlalchemy_impl import SQLAlchemyWorkflowRunRepository
                logger.info("Using SQLAlchemy repository implementation")
                db_url = os.environ.get("DATABASE_URL", "sqlite:///data/tutor_runs.db")
                _impl_cache = SQLAlchemyWorkflowRunRepository(db_url=db_url)

    return _impl_cache


def reset_repository() -> None:
    """Reset the cached repository instance.

    Useful for testing or when you need to reinitialize the repository
    with different configuration.
    """
    global _impl_cache
    _impl_cache = None
    logger.debug("Repository cache reset")
