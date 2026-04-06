"""pytest 配置和共享 fixtures"""

import asyncio
import inspect
import os
import tempfile
from pathlib import Path

import pytest


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


def pytest_pyfunc_call(pyfuncitem):
    """轻量级 asyncio 支持，避免测试环境缺少 pytest-asyncio 时无法运行 async 测试。"""
    test_func = pyfuncitem.obj
    if inspect.iscoroutinefunction(test_func):
        sig = inspect.signature(test_func)
        accepted_args = {
            name: value
            for name, value in pyfuncitem.funcargs.items()
            if name in sig.parameters
        }
        # 使用 asyncio.run 管理事件循环生命周期，避免手动 close 导致的 FD 警告
        asyncio.run(test_func(**accepted_args))
        return True
    return None
