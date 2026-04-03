"""Database migration management for TutorClaw."""

from __future__ import annotations

import importlib.util
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of a migration operation."""

    success: bool
    from_version: int
    to_version: int
    applied: List[int]
    errors: List[str]


class MigrationManager:
    """Manage database schema migrations for TutorClaw."""

    def __init__(
        self,
        db_path: Path,
        migrations_dir: Path,
    ) -> None:
        """
        Initialize MigrationManager.

        Args:
            db_path: Path to SQLite database
            migrations_dir: Directory containing migration files
        """
        self.db_path = Path(db_path).absolute()
        self.migrations_dir = Path(migrations_dir).absolute()
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

    def current_version(self) -> int:
        """
        Get the current database schema version.

        Returns:
            Current version number (0 if no migrations applied)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='_schema_versions'
            """
            )
            table_exists = cursor.fetchone() is not None

            if not table_exists:
                conn.close()
                return 0

            cursor.execute("SELECT version FROM _schema_versions ORDER BY version DESC LIMIT 1")
            result = cursor.fetchone()
            conn.close()

            return result[0] if result else 0

        except Exception as e:
            logger.error(f"Failed to get current version: {e}")
            return 0

    def migrate(self, target: Optional[int] = None) -> MigrationResult:
        """
        Run pending migrations to reach target version.

        Args:
            target: Target version (default: latest available)

        Returns:
            MigrationResult with details
        """
        current = self.current_version()
        available = self._get_available_migrations()

        if target is None:
            target = max([m[0] for m in available]) if available else current

        if target < current:
            return MigrationResult(
                success=False,
                from_version=current,
                to_version=current,
                applied=[],
                errors=["Cannot migrate backwards, use rollback()"],
            )

        if target == current:
            logger.info(f"Already at target version: {current}")
            return MigrationResult(
                success=True,
                from_version=current,
                to_version=current,
                applied=[],
                errors=[],
            )

        applied = []
        errors = []

        # Apply migrations in order
        for version, migration_file in sorted(available):
            if version <= current:
                continue

            if version > target:
                break

            try:
                logger.info(f"Applying migration: {migration_file.name}")
                self._apply_migration(migration_file, version)
                applied.append(version)
            except Exception as e:
                error_msg = f"Migration {version} failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                break

        success = len(errors) == 0
        to_version = applied[-1] if applied else current

        return MigrationResult(
            success=success,
            from_version=current,
            to_version=to_version,
            applied=applied,
            errors=errors,
        )

    def rollback(self, steps: int = 1) -> MigrationResult:
        """
        Rollback migrations by specified number of steps.

        Note: This requires that each migration has a downgrade() function.

        Args:
            steps: Number of migrations to rollback

        Returns:
            MigrationResult with details
        """
        current = self.current_version()

        if current == 0:
            return MigrationResult(
                success=True,
                from_version=0,
                to_version=0,
                applied=[],
                errors=[],
            )

        available = self._get_available_migrations()
        applied_versions = [v for v, _ in available if v <= current]
        applied_versions.sort(reverse=True)

        to_rollback = applied_versions[:steps]
        rolled_back = []
        errors = []

        for version in to_rollback:
            migration_file = self._find_migration_file(version)
            if not migration_file:
                errors.append(f"Migration file not found for version {version}")
                continue

            try:
                logger.info(f"Rolling back migration: {migration_file.name}")
                self._rollback_migration(migration_file, version)
                rolled_back.append(version)
            except Exception as e:
                error_msg = f"Rollback {version} failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                break

        success = len(errors) == 0
        final_version = current - len(rolled_back)

        return MigrationResult(
            success=success,
            from_version=current,
            to_version=final_version,
            applied=rolled_back,
            errors=errors,
        )

    def _get_available_migrations(self) -> List[tuple[int, Path]]:
        """Get list of available migration files with version numbers."""
        migrations = []

        for migration_file in self.migrations_dir.glob("*.py"):
            # Extract version from filename (e.g., 001_create_cost_entries.py)
            try:
                version_str = migration_file.stem.split("_")[0]
                version = int(version_str)
                migrations.append((version, migration_file))
            except (ValueError, IndexError):
                logger.warning(f"Invalid migration filename: {migration_file.name}")

        migrations.sort(key=lambda x: x[0])
        return migrations

    def _find_migration_file(self, version: int) -> Optional[Path]:
        """Find migration file by version number."""
        available = self._get_available_migrations()
        for v, path in available:
            if v == version:
                return path
        return None

    def _apply_migration(self, migration_file: Path, version: int) -> None:
        """Apply a single migration."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Load and execute upgrade
            spec = importlib.util.spec_from_file_location(
                "migration", migration_file
            )
            if spec and spec.loader:
                migration_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration_module)

                if hasattr(migration_module, "upgrade"):
                    migration_module.upgrade(conn)
                else:
                    raise ValueError(f"No upgrade() function in {migration_file.name}")

                # Record migration
                cursor = conn.cursor()

                # Ensure _schema_versions table exists
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS _schema_versions (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL,
                        name TEXT NOT NULL
                    )
                """
                )

                # Record this migration
                cursor.execute(
                    """
                    INSERT INTO _schema_versions (version, applied_at, name)
                    VALUES (?, ?, ?)
                """,
                    (version, datetime.now(timezone.utc).isoformat(), migration_file.name),
                )

                conn.commit()
            else:
                raise ValueError(f"Failed to load migration: {migration_file.name}")

        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _rollback_migration(self, migration_file: Path, version: int) -> None:
        """Rollback a single migration."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Load and execute downgrade
            spec = importlib.util.spec_from_file_location(
                "migration", migration_file
            )
            if spec and spec.loader:
                migration_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration_module)

                if hasattr(migration_module, "downgrade"):
                    migration_module.downgrade(conn)
                else:
                    raise ValueError(f"No downgrade() function in {migration_file.name}")

                # Remove migration record
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM _schema_versions WHERE version = ?",
                    (version,),
                )

                conn.commit()
            else:
                raise ValueError(f"Failed to load migration: {migration_file.name}")

        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()


def create_migration(name: str, migrations_dir: Path) -> Path:
    """
    Create a new migration file.

    Args:
        name: Descriptive name for the migration (e.g., "add_workflow_tags")
        migrations_dir: Directory to create migration in

    Returns:
        Path to the created migration file
    """
    migrations_dir = Path(migrations_dir).absolute()
    migrations_dir.mkdir(parents=True, exist_ok=True)

    # Get next version number
    existing = sorted(migrations_dir.glob("*.py"))
    next_version = len(existing) + 1
    version_str = f"{next_version:03d}"
    filename = f"{version_str}_{name}.py"
    migration_path = migrations_dir / filename

    # Create migration template
    template = f'''"""Migration {version_str}: {name}"""

import sqlite3
from typing import Connection


def upgrade(conn: Connection) -> None:
    """Apply this migration."""
    # TODO: Add your migration SQL here
    # cursor = conn.cursor()
    # cursor.execute("YOUR SQL HERE")
    # conn.commit()
    pass


def downgrade(conn: Connection) -> None:
    """Rollback this migration."""
    # TODO: Add your rollback SQL here
    # cursor = conn.cursor()
    # cursor.execute("YOUR ROLLBACK SQL HERE")
    # conn.commit()
    pass
'''

    migration_path.write_text(template)
    logger.info(f"Created migration: {migration_path}")
    return migration_path
