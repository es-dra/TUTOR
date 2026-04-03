"""ObsidianSync 单元测试"""

import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from tutor.core.external.obsidian import ObsidianSync


@pytest.fixture
def vault(tmp_path):
    sync = ObsidianSync(vault_path=str(tmp_path / "vault"))
    sync.initialize()
    return sync


class TestSanitizeFilename:
    def setup_method(self):
        self.sync = ObsidianSync(vault_path="/tmp/test")

    def test_normal_title(self):
        assert self.sync._sanitize_filename("Hello World") == "Hello World"

    def test_slash_replaced(self):
        assert self.sync._sanitize_filename("A/B/C") == "A_B_C"

    def test_colon_replaced(self):
        assert self.sync._sanitize_filename("10:30 Meeting") == "10_30 Meeting"

    def test_long_title_truncated(self):
        result = self.sync._sanitize_filename("A" * 300)
        assert len(result) <= 200


class TestBuildFrontmatter:
    def setup_method(self):
        self.sync = ObsidianSync(vault_path="/tmp/test")

    def test_basic_frontmatter(self):
        fm = self.sync._build_frontmatter()
        assert "---" in fm
        assert "tags:" not in fm  # no tags provided

    def test_with_tags(self):
        fm = self.sync._build_frontmatter(tags=["research", "ml"])
        assert "tags: [research, ml]" in fm

    def test_with_extra(self):
        fm = self.sync._build_frontmatter(extra={"priority": "high", "count": 42})
        assert "priority: high" in fm
        assert "count: 42" in fm


class TestSyncNote:
    def test_create_note(self, vault, tmp_path):
        path = vault.sync_note(
            title="Test Note",
            content="# Hello\n\nThis is a test.",
            tags=["test"],
        )
        assert path.exists()
        text = path.read_text()
        assert "Test Note" in str(path)
        assert "# Hello" in text
        assert "---" in text
        assert "tags: [test]" in text

    def test_subfolder(self, vault):
        path = vault.sync_note(
            title="Research Note",
            content="Content",
            folder="Research",
        )
        assert "Research" in str(path)
        assert path.exists()

    def test_no_overwrite(self, vault):
        path1 = vault.sync_note(title="Dup", content="v1", overwrite=True)
        path2 = vault.sync_note(title="Dup", content="v2", overwrite=False)
        assert path1 == path2
        assert path1.read_text().count("v1") >= 1  # still v1

    def test_special_chars_in_title(self, vault):
        path = vault.sync_note(title="A/B:C*D?", content="ok")
        assert path.exists()
        assert "/" not in path.name


class TestSyncWorkflowResult:
    def test_workflow_note(self, vault):
        path = vault.sync_workflow_result(
            workflow_type="idea",
            run_id="run-001",
            result_summary="Generated 5 ideas",
        )
        assert path.exists()
        text = path.read_text()
        assert "idea" in text
        assert "run-001" in text
        assert "Generated 5 ideas" in text


class TestSyncDecision:
    def test_adr_note(self, vault):
        path = vault.sync_decision(
            adr_id="001",
            title="Use FastAPI",
            context="Need a web framework",
            decision="Chose FastAPI",
            consequences="Good DX",
        )
        assert path.exists()
        text = path.read_text()
        assert "ADR-001" in str(path)
        assert "## Context" in text
        assert "## Decision" in text


class TestListNotes:
    def test_list_all(self, vault):
        vault.sync_note(title="Note 1", content="c1")
        vault.sync_note(title="Note 2", content="c2", folder="Research")
        notes = vault.list_notes()
        assert len(notes) == 2

    def test_list_by_folder(self, vault):
        vault.sync_note(title="Note 1", content="c1")
        vault.sync_note(title="Note 2", content="c2", folder="Research")
        notes = vault.list_notes(folder="Research")
        assert len(notes) == 1

    def test_list_by_tag(self, vault):
        vault.sync_note(title="Tagged", content="c", tags=["important"])
        vault.sync_note(title="Untagged", content="c")
        notes = vault.list_notes(tag="important")
        assert len(notes) == 1
