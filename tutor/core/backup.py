"""Backup and restore management for TutorClaw."""

from __future__ import annotations

import json
import logging
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BackupInfo:
    """Information about a backup."""

    id: str
    timestamp: str
    size_bytes: int
    description: str
    path: Path

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
            "description": self.description,
            "path": str(self.path),
        }

    @classmethod
    def from_dict(cls, data: dict) -> BackupInfo:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            size_bytes=data["size_bytes"],
            description=data["description"],
            path=Path(data["path"]),
        )


@dataclass
class BackupResult:
    """Result of a backup operation."""

    success: bool
    backup_info: Optional[BackupInfo] = None
    error: Optional[str] = None


class BackupManager:
    """Manage backup and restore operations for TutorClaw data."""

    def __init__(
        self,
        data_dir: Path,
        backup_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize BackupManager.

        Args:
            data_dir: Directory to backup (typically the data/ directory)
            backup_dir: Directory to store backups (default: data_dir/backups)
        """
        self.data_dir = Path(data_dir).absolute()
        self.backup_dir = (
            Path(backup_dir).absolute()
            if backup_dir
            else self.data_dir / "backups"
        )
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.backup_dir / "manifest.json"

    def create(self, description: str = "") -> BackupResult:
        """
        Create a backup of the data directory.

        Args:
            description: Optional description for the backup

        Returns:
            BackupResult with backup info or error
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            backup_id = f"backup_{timestamp.replace(':', '-').replace('.', '-')}"
            backup_filename = f"tutor_backup_{timestamp.replace(':', '-').replace('.', '-')}.tar.gz"
            backup_path = self.backup_dir / backup_filename

            # Create tar.gz backup
            logger.info(f"Creating backup: {backup_id}")
            with tarfile.open(backup_path, "w:gz") as tar:
                for item in self.data_dir.iterdir():
                    if item.name == "backups":  # Skip backups directory
                        continue
                    if item.is_file() or item.is_dir():
                        tar.add(item, arcname=item.name, recursive=True)

            size_bytes = backup_path.stat().st_size
            backup_info = BackupInfo(
                id=backup_id,
                timestamp=timestamp,
                size_bytes=size_bytes,
                description=description,
                path=backup_path,
            )

            # Update manifest
            self._update_manifest(backup_info)

            logger.info(f"Backup created: {backup_id} ({size_bytes} bytes)")
            return BackupResult(success=True, backup_info=backup_info)

        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            return BackupResult(success=False, error=str(e))

    def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups.

        Returns:
            List of BackupInfo objects
        """
        try:
            if not self.manifest_path.exists():
                return []

            with open(self.manifest_path, "r") as f:
                manifest = json.load(f)

            backups = [BackupInfo.from_dict(item) for item in manifest.get("backups", [])]
            return sorted(backups, key=lambda b: b.timestamp, reverse=True)

        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []

    def restore(
        self,
        backup_id: str,
        target_dir: Optional[Path] = None,
    ) -> Path:
        """
        Restore from a backup.

        Args:
            backup_id: ID of the backup to restore
            target_dir: Target directory for restore (default: original data_dir)

        Returns:
            Path to restored directory

        Raises:
            FileNotFoundError: If backup not found
            ValueError: If backup file is invalid
        """
        backup_info = self._find_backup(backup_id)
        if not backup_info:
            raise FileNotFoundError(f"Backup not found: {backup_id}")

        target = Path(target_dir).absolute() if target_dir else self.data_dir

        logger.info(f"Restoring backup: {backup_id} to {target}")

        # Verify tar file integrity before extraction
        try:
            with tarfile.open(backup_info.path, "r:gz") as tar:
                tar.getmembers()  # This validates the archive
        except tarfile.TarError as e:
            raise ValueError(f"Invalid backup file: {e}")

        # Extract backup
        try:
            with tarfile.open(backup_info.path, "r:gz") as tar:
                tar.extractall(target)

            logger.info(f"Backup restored successfully: {backup_id}")
            return target

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise

    def cleanup(self, keep_last: int = 5) -> List[str]:
        """
        Clean up old backups, keeping only the most recent N.

        Args:
            keep_last: Number of recent backups to keep

        Returns:
            List of backup IDs that were removed
        """
        backups = self.list_backups()

        if len(backups) <= keep_last:
            return []

        to_remove = backups[keep_last:]
        removed_ids = []

        for backup in to_remove:
            try:
                backup.path.unlink()
                removed_ids.append(backup.id)
                logger.info(f"Removed old backup: {backup.id}")
            except Exception as e:
                logger.error(f"Failed to remove backup {backup.id}: {e}")

        # Update manifest
        self._update_manifest_from_list([b for b in backups if b.id not in removed_ids])

        return removed_ids

    def _find_backup(self, backup_id: str) -> Optional[BackupInfo]:
        """Find backup by ID."""
        backups = self.list_backups()
        for backup in backups:
            if backup.id == backup_id:
                return backup
        return None

    def _update_manifest(self, backup_info: BackupInfo) -> None:
        """Add backup to manifest file."""
        backups = self.list_backups()

        # Remove existing entry with same ID (if any)
        backups = [b for b in backups if b.id != backup_info.id]

        # Add new entry
        backups.append(backup_info)

        # Sort by timestamp
        backups = sorted(backups, key=lambda b: b.timestamp, reverse=True)

        # Write manifest
        self._update_manifest_from_list(backups)

    def _update_manifest_from_list(self, backups: List[BackupInfo]) -> None:
        """Write manifest from list of BackupInfo."""
        manifest = {
            "version": "1.0",
            "backups": [b.to_dict() for b in backups],
        }

        with open(self.manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
