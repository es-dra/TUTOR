"""TUTOR Config Loader

从 tutor.config 导入并重新导出，保持向后兼容。
"""

from . import load_config, ConfigError

__all__ = ['load_config', 'ConfigError']
