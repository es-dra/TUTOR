"""pytest 配置和共享 fixtures"""

import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_db_path(tmp_path):
    """提供临时数据库路径，确保每次测试使用干净的数据库"""
    db_file = tmp_path / "test_runs.db"
    yield str(db_file)
    # 清理
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
def temp_data_dir(tmp_path):
    """提供临时数据目录"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    yield data_dir
