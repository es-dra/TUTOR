"""TUTOR 配置管理模块"""

from pathlib import Path
import yaml
import os
from typing import Dict, Any

__all__ = ['load_config', 'ConfigError']


class ConfigError(Exception):
    """配置错误"""
    pass


def load_config(config_path: Path = None) -> Dict[str, Any]:
    """
    加载TUTOR配置文件
    
    搜索顺序：
    1. 显式指定的config_path
    2. 环境变量TUTOR_CONFIG
    3. 项目根目录config/config.yaml
    4. 项目根目录config.yaml
    
    Returns:
        配置字典（包含model, storage, workflow, logging, cli等键）
    """
    # 确定配置文件路径
    if config_path:
        config_file = Path(config_path)
    else:
        # 从环境变量查找
        env_config = os.getenv("TUTOR_CONFIG")
        if env_config:
            config_file = Path(env_config)
        else:
            # 默认搜索路径
            possible_paths = [
                Path("config/config.yaml"),
                Path("config.yaml"),
                Path(__file__).parent.parent / "config" / "config.yaml"
            ]
            config_file = None
            for p in possible_paths:
                if p.exists():
                    config_file = p
                    break
            
            if not config_file:
                raise ConfigError(
                    "配置文件未找到。请确保config/config.yaml存在，"
                    "或设置TUTOR_CONFIG环境变量。"
                )
    
    # 读取并解析YAML
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not isinstance(config, dict):
            raise ConfigError(f"配置文件格式错误：{config_file}")
        
        # 处理API密钥环境变量替换
        _substitute_env_vars(config)
        
        return config
        
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML解析错误：{e}")
    except IOError as e:
        raise ConfigError(f"配置文件读取失败：{e}")


def _substitute_env_vars(config: Dict[str, Any]) -> None:
    """
    替换配置中的环境变量占位符
    例如：api_key: "${OPENAI_API_KEY}" 会被替换为实际环境变量值
    """
    def _substitute(value):
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            return os.getenv(env_var, value)  # 如果环境变量不存在，保持原样
        elif isinstance(value, dict):
            return {k: _substitute(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [_substitute(item) for item in value]
        else:
            return value
    
    # 递归替换
    for key, val in config.items():
        config[key] = _substitute(val)
