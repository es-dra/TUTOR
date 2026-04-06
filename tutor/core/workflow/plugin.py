"""TUTOR 工作流插件系统

支持工作流的插件化扩展，允许用户自定义工作流步骤和功能。
"""

import importlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional, Type

logger = logging.getLogger(__name__)


class WorkflowPlugin(ABC):
    """工作流插件抽象基类
    
    所有工作流插件都应继承此类。
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """插件版本"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """插件描述"""
        pass
    
    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化插件
        
        Args:
            config: 插件配置
        """
        pass
    
    def shutdown(self) -> None:
        """关闭插件"""
        pass
    
    def get_workflow_steps(self) -> List[Type['WorkflowStep']]:
        """获取插件提供的工作流步骤
        
        Returns:
            工作流步骤类列表
        """
        return []
    
    def get_workflow_types(self) -> Dict[str, Type['Workflow']]:
        """获取插件提供的工作流类型
        
        Returns:
            工作流类型字典，键为工作流类型名称，值为工作流类
        """
        return {}
    
    def get_hooks(self) -> Dict[str, List[callable]]:
        """获取插件提供的钩子函数
        
        Returns:
            钩子函数字典，键为钩子名称，值为钩子函数列表
        """
        return {}


class PluginManager:
    """插件管理器
    
    负责插件的加载、注册和管理。
    """
    
    def __init__(self):
        self.plugins: Dict[str, WorkflowPlugin] = {}
        self.hooks: Dict[str, List[callable]] = {}
        self.plugin_paths: List[Path] = []
    
    def add_plugin_path(self, path: Path) -> None:
        """添加插件路径
        
        Args:
            path: 插件路径
        """
        if path.exists() and path not in self.plugin_paths:
            self.plugin_paths.append(path)
            logger.info(f"Added plugin path: {path}")
    
    def load_plugins(self) -> List[str]:
        """加载所有插件
        
        Returns:
            加载的插件名称列表
        """
        loaded_plugins = []
        
        # 加载内置插件
        self._load_builtin_plugins()
        
        # 加载外部插件
        for plugin_path in self.plugin_paths:
            loaded = self._load_plugins_from_path(plugin_path)
            loaded_plugins.extend(loaded)
        
        # 初始化所有插件
        for plugin_name, plugin in self.plugins.items():
            try:
                plugin.initialize({})
                loaded_plugins.append(plugin_name)
                logger.info(f"Initialized plugin: {plugin_name}")
            except Exception as e:
                logger.error(f"Failed to initialize plugin {plugin_name}: {e}")
        
        # 注册钩子
        self._register_hooks()
        
        return loaded_plugins
    
    def _load_builtin_plugins(self) -> None:
        """加载内置插件"""
        # 这里可以添加内置插件的加载逻辑
        pass
    
    def _load_plugins_from_path(self, path: Path) -> List[str]:
        """从指定路径加载插件
        
        Args:
            path: 插件路径
        
        Returns:
            加载的插件名称列表
        """
        loaded_plugins = []
        
        if not path.exists():
            return loaded_plugins
        
        # 遍历路径下的所有Python文件
        for py_file in path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                # 动态导入模块
                module_name = f"plugin_{py_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, str(py_file))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # 查找插件类
                    for name, obj in module.__dict__.items():
                        if (isinstance(obj, type) and 
                            issubclass(obj, WorkflowPlugin) and 
                            obj != WorkflowPlugin):
                            # 创建插件实例
                            plugin = obj()
                            self.plugins[plugin.name] = plugin
                            loaded_plugins.append(plugin.name)
                            logger.info(f"Loaded plugin: {plugin.name} from {py_file}")
                            break
            except Exception as e:
                logger.error(f"Failed to load plugin from {py_file}: {e}")
        
        return loaded_plugins
    
    def _register_hooks(self) -> None:
        """注册所有插件的钩子函数"""
        for plugin_name, plugin in self.plugins.items():
            try:
                plugin_hooks = plugin.get_hooks()
                for hook_name, hook_functions in plugin_hooks.items():
                    if hook_name not in self.hooks:
                        self.hooks[hook_name] = []
                    self.hooks[hook_name].extend(hook_functions)
                    logger.info(f"Registered {len(hook_functions)} hooks for {hook_name} from {plugin_name}")
            except Exception as e:
                logger.error(f"Failed to register hooks for plugin {plugin_name}: {e}")
    
    def get_plugin(self, name: str) -> Optional[WorkflowPlugin]:
        """获取指定名称的插件
        
        Args:
            name: 插件名称
        
        Returns:
            插件实例，不存在则返回None
        """
        return self.plugins.get(name)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """列出所有加载的插件
        
        Returns:
            插件信息列表
        """
        plugin_list = []
        for name, plugin in self.plugins.items():
            plugin_list.append({
                "name": name,
                "version": plugin.version,
                "description": plugin.description
            })
        return plugin_list
    
    def get_workflow_steps(self) -> List[Type['WorkflowStep']]:
        """获取所有插件提供的工作流步骤
        
        Returns:
            工作流步骤类列表
        """
        steps = []
        for plugin in self.plugins.values():
            try:
                plugin_steps = plugin.get_workflow_steps()
                steps.extend(plugin_steps)
            except Exception as e:
                logger.error(f"Failed to get workflow steps from plugin {plugin.name}: {e}")
        return steps
    
    def get_workflow_types(self) -> Dict[str, Type['Workflow']]:
        """获取所有插件提供的工作流类型
        
        Returns:
            工作流类型字典
        """
        workflow_types = {}
        for plugin in self.plugins.values():
            try:
                plugin_workflows = plugin.get_workflow_types()
                workflow_types.update(plugin_workflows)
            except Exception as e:
                logger.error(f"Failed to get workflow types from plugin {plugin.name}: {e}")
        return workflow_types
    
    def execute_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """执行指定的钩子
        
        Args:
            hook_name: 钩子名称
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            钩子函数的返回值列表
        """
        results = []
        if hook_name in self.hooks:
            for hook_func in self.hooks[hook_name]:
                try:
                    result = hook_func(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to execute hook {hook_name}: {e}")
        return results
    
    def shutdown(self) -> None:
        """关闭所有插件"""
        for plugin_name, plugin in self.plugins.items():
            try:
                plugin.shutdown()
                logger.info(f"Shutdown plugin: {plugin_name}")
            except Exception as e:
                logger.error(f"Failed to shutdown plugin {plugin_name}: {e}")
        self.plugins.clear()
        self.hooks.clear()


# 全局插件管理器实例
_plugin_manager = None

def get_plugin_manager() -> PluginManager:
    """获取全局插件管理器实例
    
    Returns:
        插件管理器实例
    """
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager

def initialize_plugins() -> List[str]:
    """初始化插件系统
    
    Returns:
        加载的插件名称列表
    """
    manager = get_plugin_manager()
    
    # 添加默认插件路径
    default_plugin_path = Path(__file__).parent / "plugins"
    manager.add_plugin_path(default_plugin_path)
    
    # 添加用户插件路径
    user_plugin_path = Path.home() / ".tutor" / "plugins"
    manager.add_plugin_path(user_plugin_path)
    
    # 加载插件
    return manager.load_plugins()


__all__ = [
    'WorkflowPlugin',
    'PluginManager',
    'get_plugin_manager',
    'initialize_plugins'
]
