"""Storage Manager Unit Tests - 存储管理器测试"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from tutor.core.storage.base import StorageBackend, StorageMetadata, StorageError
from tutor.core.storage.file_backend import FileBackend
from tutor.core.storage.sqlite_backend import SQLiteBackend
from tutor.core.storage import StorageManager


class TestStorageMetadata:
    """StorageMetadata测试"""
    
    def test_metadata_creation(self):
        """测试元数据创建"""
        meta = StorageMetadata(
            id="test-123",
            type="idea",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z"
        )
        assert meta.id == "test-123"
        assert meta.type == "idea"
        assert meta.tags == []
        assert meta.extra == {}
    
    def test_metadata_with_extra(self):
        """测试带额外字段的元数据"""
        meta = StorageMetadata(
            id="test-456",
            type="workflow",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            tags=["research", "ai"],
            extra={"score": 0.85, "author": "test"}
        )
        assert meta.tags == ["research", "ai"]
        assert meta.extra["score"] == 0.85
        assert meta.extra["author"] == "test"


class TestFileBackend:
    """FileBackend测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        shutil.rmtree(tmp)
    
    @pytest.fixture
    def file_backend(self, temp_dir):
        """文件后端实例"""
        return FileBackend(temp_dir)
    
    def test_initialize_creates_directories(self, file_backend, temp_dir):
        """测试初始化创建目录"""
        file_backend.initialize()
        assert (temp_dir / "data").exists()
        assert (temp_dir / "metadata").exists()
    
    def test_save_and_load(self, file_backend):
        """测试保存和加载数据"""
        file_backend.initialize()
        
        data = {"title": "Test Idea", "description": "A test idea"}
        resource_id = file_backend.save(
            data=data,
            resource_type="idea",
            resource_id="test-001"
        )
        
        assert resource_id == "test-001"
        
        loaded = file_backend.load("idea", "test-001")
        assert loaded == data
    
    def test_save_with_metadata(self, file_backend):
        """测试带元数据的保存"""
        file_backend.initialize()
        
        meta = StorageMetadata(
            id="test-002",
            type="idea",
            created_at=datetime.now(timezone.utc).isoformat() + "Z",
            updated_at=datetime.now(timezone.utc).isoformat() + "Z",
            tags=["test", "example"]
        )
        
        data = {"key": "value"}
        file_backend.save(data, "idea", "test-002", meta)
        
        # 加载并验证元数据
        loaded, loaded_meta = file_backend.load("idea", "test-002", return_metadata=True)
        assert loaded == data
        assert loaded_meta.id == "test-002"
        assert "test" in loaded_meta.tags
    
    def test_exists(self, file_backend):
        """测试存在性检查"""
        file_backend.initialize()
        
        assert not file_backend.exists("idea", "nonexistent")
        
        file_backend.save({"data": 123}, "idea", "exists-test")
        assert file_backend.exists("idea", "exists-test")
    
    def test_delete(self, file_backend):
        """测试删除"""
        file_backend.initialize()
        
        file_backend.save({"data": 123}, "idea", "delete-test")
        assert file_backend.exists("idea", "delete-test")
        
        deleted = file_backend.delete("idea", "delete-test")
        assert deleted is True
        assert not file_backend.exists("idea", "delete-test")
        
        # 删除不存在的资源应返回False
        deleted = file_backend.delete("idea", "nonexistent")
        assert deleted is False
    
    def test_list(self, file_backend):
        """测试列出资源"""
        file_backend.initialize()
        
        # 保存多个资源
        file_backend.save({"id": 1}, "idea", "idea-1", StorageMetadata(
            id="idea-1", type="idea", created_at="2024-01-01T00:00:00Z", updated_at="2024-01-01T00:00:00Z", tags=["a"]
        ))
        file_backend.save({"id": 2}, "idea", "idea-2", StorageMetadata(
            id="idea-2", type="idea", created_at="2024-01-02T00:00:00Z", updated_at="2024-01-02T00:00:00Z", tags=["b"]
        ))
        file_backend.save({"id": 3}, "experiment", "exp-1", StorageMetadata(
            id="exp-1", type="experiment", created_at="2024-01-03T00:00:00Z", updated_at="2024-01-03T00:00:00Z", tags=["a"]
        ))
        
        # 列出所有idea
        ideas = file_backend.list("idea")
        assert len(ideas) == 2
        assert {item["id"] for item in ideas} == {"idea-1", "idea-2"}
        
        # 按标签过滤
        ideas_tag_a = file_backend.list("idea", filter_tags=["a"])
        assert len(ideas_tag_a) == 1
        assert ideas_tag_a[0]["id"] == "idea-1"


class TestSQLiteBackend:
    """SQLiteBackend测试"""
    
    @pytest.fixture
    def temp_db(self):
        """临时数据库"""
        tmp = tempfile.mktemp(suffix=".db")
        yield tmp
        Path(tmp).unlink(missing_ok=True)
    
    @pytest.fixture
    def sqlite_backend(self, temp_db):
        """SQLite后端实例"""
        backend = SQLiteBackend(f"sqlite:///{temp_db}")
        yield backend
        # 确保关闭连接，避免 Windows 文件锁导致清理失败
        backend.close()
    
    def test_initialize_creates_tables(self, sqlite_backend):
        """测试初始化创建表"""
        sqlite_backend.initialize()
        
        # 验证表存在
        conn = sqlite_backend._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='resources'"
        )
        assert cursor.fetchone() is not None
        
        conn.close()
    
    def test_save_and_load(self, sqlite_backend):
        """测试保存和加载"""
        sqlite_backend.initialize()
        
        data = {"title": "Test", "value": 42}
        resource_id = sqlite_backend.save(
            data=data,
            resource_type="workflow",
            resource_id="wf-001"
        )
        
        assert resource_id == "wf-001"
        
        loaded = sqlite_backend.load("workflow", "wf-001")
        assert loaded == data
    
    def test_metadata_query(self, sqlite_backend):
        """测试元数据查询"""
        sqlite_backend.initialize()
        
        meta = StorageMetadata(
            id="wf-002",
            type="workflow",
            created_at=datetime.now(timezone.utc).isoformat() + "Z",
            updated_at=datetime.now(timezone.utc).isoformat() + "Z",
            tags=["completed", "test"],
            extra={"duration": 120}
        )
        
        sqlite_backend.save({"status": "done"}, "workflow", "wf-002", meta)
        
        # 列出并过滤
        workflows = sqlite_backend.list("workflow", filter_tags=["completed"])
        assert len(workflows) == 1
        assert workflows[0]["id"] == "wf-002"
        assert "completed" in workflows[0]["tags"]
        assert workflows[0]["extra"]["duration"] == 120
    
    def test_delete(self, sqlite_backend):
        """测试删除"""
        sqlite_backend.initialize()
        
        sqlite_backend.save({"data": "test"}, "idea", "idea-delete")
        assert sqlite_backend.exists("idea", "idea-delete")
        
        deleted = sqlite_backend.delete("idea", "idea-delete")
        assert deleted
        assert not sqlite_backend.exists("idea", "idea-delete")


class TestStorageManager:
    """StorageManager集成测试"""
    
    @pytest.fixture
    def temp_project_dir(self):
        """临时项目目录"""
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        import gc; gc.collect()  # 强制 GC 关闭 SQLite 连接
        shutil.rmtree(tmp, ignore_errors=True)
    
    @pytest.fixture
    def storage_manager(self, temp_project_dir):
        """StorageManager实例"""
        config = {
            "storage": {
                "database": f"sqlite:///{temp_project_dir}/tutor.db",
                "project_dir": str(temp_project_dir / "projects")
            }
        }
        manager = StorageManager(config)
        yield manager
        # 确保关闭所有后端连接
        try:
            manager.close()
        except Exception:
            pass
    
    def test_initialization(self, storage_manager):
        """测试初始化"""
        storage_manager.initialize()
        assert storage_manager.sqlite_backend is not None
        assert storage_manager.file_backend is not None
        assert (storage_manager.project_dir).exists()
    
    def test_save_and_load_workflow(self, storage_manager):
        """测试工作流保存和加载"""
        storage_manager.initialize()
        
        workflow_data = {
            "type": "idea",
            "status": "completed",
            "recommended_idea": {"title": "Test Idea"}
        }
        
        storage_manager.save_workflow(
            workflow_id="wf-test-001",
            workflow_type="IdeaFlow",
            config={"debate_rounds": 2},
            result=workflow_data
        )
        
        # 加载工作流
        loaded = storage_manager.load_workflow("wf-test-001")
        assert loaded is not None
        assert loaded["type"] == "idea"
        assert loaded["result"]["recommended_idea"]["title"] == "Test Idea"
    
    def test_list_workflows(self, storage_manager):
        """测试列出工作流"""
        storage_manager.initialize()
        
        # 创建多个工作流
        for i in range(5):
            storage_manager.save_workflow(
                workflow_id=f"wf-{i:03d}",
                workflow_type="IdeaFlow",
                config={"debate_rounds": 2},
                result={"index": i}
            )
        
        workflows = storage_manager.list_workflows()
        assert len(workflows) == 5
        
        # 按类型过滤
        idea_flows = storage_manager.list_workflows(workflow_type="IdeaFlow")
        assert len(idea_flows) == 5
    
    def test_project_isolation(self, storage_manager):
        """测试项目隔离"""
        storage_manager.initialize()
        
        # 不同的项目应相互隔离
        proj1_id = "project-001"
        proj2_id = "project-002"
        
        storage_manager.save_workflow(
            workflow_id="wf-shared",
            workflow_type="IdeaFlow",
            config={},
            result={"project": proj1_id},
            project_id=proj1_id
        )
        
        storage_manager.save_workflow(
            workflow_id="wf-shared",
            workflow_type="ExperimentFlow",
            config={},
            result={"project": proj2_id},
            project_id=proj2_id
        )
        
        # 应该能分别加载
        wf1 = storage_manager.load_workflow("wf-shared", project_id=proj1_id)
        wf2 = storage_manager.load_workflow("wf-shared", project_id=proj2_id)
        
        assert wf1["result"]["project"] == proj1_id
        assert wf2["result"]["project"] == proj2_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
