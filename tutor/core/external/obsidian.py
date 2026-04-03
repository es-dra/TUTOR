"""Obsidian集成模块

将TUTOR的研究成果、技术决策、笔记自动同步到Obsidian vault。

使用方式：
    from core.external.obsidian import ObsidianSync

    sync = ObsidianSync(vault_path="/path/to/obsidian-vault")
    sync.sync_note(title="Research Note", content="# Title\\nContent...", folder="Research")
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ObsidianSync:
    """Obsidian Vault 同步工具

    将Markdown文件同步到Obsidian vault，支持：
    - 笔记创建/更新
    - 标签管理
    - 前置元数据（frontmatter）
    - 双向链接（[[]]）
    - 文件夹组织
    """

    def __init__(self, vault_path: str, default_folder: str = "TUTOR"):
        self.vault_path = Path(vault_path)
        self.default_folder = default_folder
        self._initialized = False

    def initialize(self) -> None:
        """创建必要的文件夹结构"""
        folders = [
            self.vault_path / self.default_folder,
            self.vault_path / self.default_folder / "Research",
            self.vault_path / self.default_folder / "Decisions",
            self.vault_path / self.default_folder / "Experiments",
            self.vault_path / self.default_folder / "Reviews",
            self.vault_path / "templates",
        ]
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info(f"Obsidian vault initialized: {self.vault_path}")

    def _sanitize_filename(self, title: str) -> str:
        """将标题转为安全的文件名"""
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            title = title.replace(char, '_')
        return title.strip()[:200]

    def _build_frontmatter(
        self,
        tags: Optional[List[str]] = None,
        created: Optional[str] = None,
        updated: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建YAML前置元数据"""
        now = (updated or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        lines = ["---"]
        lines.append(f"created: {created or now}")
        lines.append(f"updated: {now}")
        if tags:
            lines.append(f"tags: [{', '.join(tags)}]")
        if extra:
            for k, v in extra.items():
                if isinstance(v, list):
                    lines.append(f"{k}: [{', '.join(str(i) for i in v)}]")
                elif isinstance(v, (str, int, float, bool)):
                    lines.append(f"{k}: {v}")
        lines.append("---")
        return "\n".join(lines)

    def sync_note(
        self,
        title: str,
        content: str,
        folder: Optional[str] = None,
        tags: Optional[List[str]] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
        overwrite: bool = True,
    ) -> Path:
        """同步笔记到Obsidian vault

        Args:
            title: 笔记标题（作为文件名）
            content: Markdown内容
            folder: 子文件夹（相对于default_folder）
            tags: 标签列表
            extra_meta: 额外前置元数据
            overwrite: 是否覆盖已有文件

        Returns:
            笔记文件路径
        """
        if not self._initialized:
            self.initialize()

        target_folder = self.vault_path / self.default_folder
        if folder:
            target_folder = target_folder / folder
        target_folder.mkdir(parents=True, exist_ok=True)

        filename = self._sanitize_filename(title) + ".md"
        file_path = target_folder / filename

        if file_path.exists() and not overwrite:
            logger.info(f"Note already exists, skipping: {file_path}")
            return file_path

        frontmatter = self._build_frontmatter(
            tags=tags, extra=extra_meta
        )
        full_content = f"{frontmatter}\n\n{content}"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        logger.info(f"Synced note: {file_path}")
        return file_path

    def sync_workflow_result(
        self,
        workflow_type: str,
        run_id: str,
        result_summary: str,
        tags: Optional[List[str]] = None,
    ) -> Path:
        """同步工作流运行结果"""
        return self.sync_note(
            title=f"{workflow_type} — {run_id}",
            content=f"# {workflow_type} Result\n\n**Run ID**: `{run_id}`\n\n{result_summary}",
            folder="Experiments",
            tags=(tags or []) + ["workflow", workflow_type, "tutor"],
            extra_meta={"run_id": run_id, "workflow_type": workflow_type},
        )

    def sync_decision(
        self,
        adr_id: str,
        title: str,
        context: str,
        decision: str,
        consequences: str = "",
        tags: Optional[List[str]] = None,
    ) -> Path:
        """同步架构决策记录（ADR）"""
        content = f"""# {title}

## Context
{context}

## Decision
{decision}

## Consequences
{consequences or "TBD"}
"""
        return self.sync_note(
            title=f"ADR-{adr_id} — {title}",
            content=content,
            folder="Decisions",
            tags=(tags or []) + ["adr", "architecture"],
            extra_meta={"adr_id": adr_id},
        )

    def list_notes(
        self,
        folder: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出vault中的笔记"""
        search_dir = self.vault_path / self.default_folder
        if folder:
            search_dir = search_dir / folder

        notes = []
        if not search_dir.exists():
            return notes

        for md_file in search_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                note = {
                    "path": str(md_file.relative_to(self.vault_path)),
                    "title": md_file.stem,
                    "size": md_file.stat().st_size,
                }

                # Parse frontmatter tags
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end > 0:
                        fm = text[3:end].strip()
                        if tag and f"[{tag}]" not in fm and f"{tag}" not in fm:
                            continue
                        note["has_frontmatter"] = True

                notes.append(note)
            except Exception as e:
                logger.debug(f"Error reading {md_file}: {e}")

        return notes
