"""TUTOR Workflow Error Handling - 错误分类与智能恢复系统

提供错误分类、智能恢复建议和错误报告功能。
"""

import json
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """错误类型枚举"""
    API_ERROR = "api_error"  # API 错误（可重试）
    LOGIC_ERROR = "logic_error"  # 逻辑错误（需修改输入）
    SYSTEM_ERROR = "system_error"  # 系统错误（需报告）
    NETWORK_ERROR = "network_error"  # 网络错误（可重试）
    VALIDATION_ERROR = "validation_error"  # 验证错误（需修改输入）


class ErrorSeverity(str, Enum):
    """错误严重程度枚举"""
    LOW = "low"  # 低严重度
    MEDIUM = "medium"  # 中等严重度
    HIGH = "high"  # 高严重度
    CRITICAL = "critical"  # 严重


@dataclass
class ErrorAnalysis:
    """错误分析结果"""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    details: Dict[str, Any]
    suggestions: List[str]
    is_retryable: bool


class ErrorClassifier:
    """错误分类器"""
    
    @staticmethod
    def classify_error(error: Exception) -> ErrorAnalysis:
        """分类错误并生成分析结果
        
        Args:
            error: 异常对象
            
        Returns:
            ErrorAnalysis: 错误分析结果
        """
        error_str = str(error)
        error_type = type(error).__name__
        
        # 分析错误类型
        if any(keyword in error_str.lower() for keyword in [
            "api", "rate limit", "429", "quota", "token limit"
        ]):
            return ErrorClassifier._classify_api_error(error, error_str, error_type)
        
        elif any(keyword in error_str.lower() for keyword in [
            "validation", "invalid", "missing", "required", "format"
        ]):
            return ErrorClassifier._classify_validation_error(error, error_str, error_type)
        
        elif any(keyword in error_str.lower() for keyword in [
            "network", "timeout", "connection", "socket", "dns"
        ]):
            return ErrorClassifier._classify_network_error(error, error_str, error_type)
        
        elif any(keyword in error_str.lower() for keyword in [
            "system", "internal", "server", "500", "database"
        ]):
            return ErrorClassifier._classify_system_error(error, error_str, error_type)
        
        else:
            return ErrorClassifier._classify_logic_error(error, error_str, error_type)
    
    @staticmethod
    def _classify_api_error(error: Exception, error_str: str, error_type: str) -> ErrorAnalysis:
        """分类 API 错误"""
        suggestions = [
            "等待一段时间后重试",
            "检查 API Key 是否有效",
            "检查 API 配额是否充足",
            "考虑使用备用模型"
        ]
        
        if "rate limit" in error_str.lower():
            suggestions.insert(0, "已达到 API 速率限制，请稍后再试")
        elif "quota" in error_str.lower():
            suggestions.insert(0, "API 配额不足，请检查账户余额")
        
        return ErrorAnalysis(
            error_type=ErrorType.API_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=f"API 错误: {error_str}",
            details={
                "error_type": error_type,
                "error_message": error_str,
                "traceback": traceback.format_exc()
            },
            suggestions=suggestions,
            is_retryable=True
        )
    
    @staticmethod
    def _classify_validation_error(error: Exception, error_str: str, error_type: str) -> ErrorAnalysis:
        """分类验证错误"""
        suggestions = [
            "检查输入参数是否正确",
            "确保所有必填字段都已填写",
            "验证输入格式是否符合要求"
        ]
        
        return ErrorAnalysis(
            error_type=ErrorType.VALIDATION_ERROR,
            severity=ErrorSeverity.LOW,
            message=f"验证错误: {error_str}",
            details={
                "error_type": error_type,
                "error_message": error_str,
                "traceback": traceback.format_exc()
            },
            suggestions=suggestions,
            is_retryable=False
        )
    
    @staticmethod
    def _classify_network_error(error: Exception, error_str: str, error_type: str) -> ErrorAnalysis:
        """分类网络错误"""
        suggestions = [
            "检查网络连接是否正常",
            "等待一段时间后重试",
            "检查 API 服务器是否可用"
        ]
        
        return ErrorAnalysis(
            error_type=ErrorType.NETWORK_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=f"网络错误: {error_str}",
            details={
                "error_type": error_type,
                "error_message": error_str,
                "traceback": traceback.format_exc()
            },
            suggestions=suggestions,
            is_retryable=True
        )
    
    @staticmethod
    def _classify_system_error(error: Exception, error_str: str, error_type: str) -> ErrorAnalysis:
        """分类系统错误"""
        suggestions = [
            "检查系统资源是否充足",
            "查看系统日志了解详细信息",
            "联系技术支持"
        ]
        
        return ErrorAnalysis(
            error_type=ErrorType.SYSTEM_ERROR,
            severity=ErrorSeverity.HIGH,
            message=f"系统错误: {error_str}",
            details={
                "error_type": error_type,
                "error_message": error_str,
                "traceback": traceback.format_exc()
            },
            suggestions=suggestions,
            is_retryable=False
        )
    
    @staticmethod
    def _classify_logic_error(error: Exception, error_str: str, error_type: str) -> ErrorAnalysis:
        """分类逻辑错误"""
        suggestions = [
            "检查输入参数是否合理",
            "查看工作流配置是否正确",
            "尝试使用不同的参数组合"
        ]
        
        return ErrorAnalysis(
            error_type=ErrorType.LOGIC_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=f"逻辑错误: {error_str}",
            details={
                "error_type": error_type,
                "error_message": error_str,
                "traceback": traceback.format_exc()
            },
            suggestions=suggestions,
            is_retryable=False
        )


class ErrorRecoveryManager:
    """错误恢复管理器"""
    
    @staticmethod
    def generate_recovery_plan(analysis: ErrorAnalysis, workflow_context: Any) -> Dict[str, Any]:
        """生成恢复计划
        
        Args:
            analysis: 错误分析结果
            workflow_context: 工作流上下文
            
        Returns:
            Dict[str, Any]: 恢复计划
        """
        recovery_plan = {
            "error_analysis": analysis.__dict__,
            "recovery_actions": [],
            "estimated_success_rate": 0.0
        }
        
        # 根据错误类型生成恢复操作
        if analysis.error_type in [ErrorType.API_ERROR, ErrorType.NETWORK_ERROR]:
            recovery_plan["recovery_actions"] = [
                {
                    "action": "retry",
                    "description": "重试当前步骤",
                    "parameters": {
                        "max_retries": 3,
                        "delay_seconds": 5
                    }
                },
                {
                    "action": "switch_model",
                    "description": "切换到备用模型",
                    "parameters": {
                        "model_type": "fallback"
                    }
                }
            ]
            recovery_plan["estimated_success_rate"] = 0.8
        
        elif analysis.error_type == ErrorType.VALIDATION_ERROR:
            recovery_plan["recovery_actions"] = [
                {
                    "action": "validate_input",
                    "description": "验证并修正输入参数",
                    "parameters": {
                        "required_fields": []
                    }
                }
            ]
            recovery_plan["estimated_success_rate"] = 0.9
        
        elif analysis.error_type == ErrorType.LOGIC_ERROR:
            recovery_plan["recovery_actions"] = [
                {
                    "action": "adjust_parameters",
                    "description": "调整工作流参数",
                    "parameters": {
                        "suggested_parameters": {}
                    }
                },
                {
                    "action": "skip_step",
                    "description": "跳过当前步骤（如果可能）",
                    "parameters": {
                        "skip_reason": "逻辑错误，无法继续"
                    }
                }
            ]
            recovery_plan["estimated_success_rate"] = 0.6
        
        elif analysis.error_type == ErrorType.SYSTEM_ERROR:
            recovery_plan["recovery_actions"] = [
                {
                    "action": "check_system",
                    "description": "检查系统状态",
                    "parameters": {
                        "checks": ["memory", "disk", "network"]
                    }
                },
                {
                    "action": "restart_service",
                    "description": "重启相关服务",
                    "parameters": {
                        "services": []
                    }
                }
            ]
            recovery_plan["estimated_success_rate"] = 0.4
        
        return recovery_plan
    
    @staticmethod
    def generate_error_report(analysis: ErrorAnalysis, workflow_context: Any) -> Dict[str, Any]:
        """生成错误报告
        
        Args:
            analysis: 错误分析结果
            workflow_context: 工作流上下文
            
        Returns:
            Dict[str, Any]: 错误报告
        """
        error_report = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "workflow_id": workflow_context.workflow_id if hasattr(workflow_context, "workflow_id") else "unknown",
            "error_analysis": analysis.__dict__,
            "workflow_context": {
                "current_step": workflow_context._current_step if hasattr(workflow_context, "_current_step") else "unknown",
                "steps": len(workflow_context.steps) if hasattr(workflow_context, "steps") else 0,
                "config": workflow_context.config if hasattr(workflow_context, "config") else {}
            },
            "environment": {
                "python_version": "3.10+",
                "tutor_version": "3.0",
                "os": "linux"
            },
            "recovery_plan": ErrorRecoveryManager.generate_recovery_plan(analysis, workflow_context)
        }
        
        return error_report
    
    @staticmethod
    def format_error_report(report: Dict[str, Any]) -> str:
        """格式化错误报告为可读字符串
        
        Args:
            report: 错误报告
            
        Returns:
            str: 格式化的错误报告
        """
        return json.dumps(report, indent=2, ensure_ascii=False)


# 便捷函数
def analyze_error(error: Exception, workflow_context: Any = None) -> ErrorAnalysis:
    """分析错误并生成分析结果
    
    Args:
        error: 异常对象
        workflow_context: 工作流上下文
        
    Returns:
        ErrorAnalysis: 错误分析结果
    """
    analysis = ErrorClassifier.classify_error(error)
    logger.info(f"Error classified: {analysis.error_type.value} - {analysis.message}")
    return analysis

def generate_recovery_suggestions(error: Exception, workflow_context: Any = None) -> List[str]:
    """生成恢复建议
    
    Args:
        error: 异常对象
        workflow_context: 工作流上下文
        
    Returns:
        List[str]: 恢复建议列表
    """
    analysis = analyze_error(error, workflow_context)
    return analysis.suggestions

def generate_error_report_dict(error: Exception, workflow_context: Any = None) -> Dict[str, Any]:
    """生成错误报告字典
    
    Args:
        error: 异常对象
        workflow_context: 工作流上下文
        
    Returns:
        Dict[str, Any]: 错误报告
    """
    analysis = analyze_error(error, workflow_context)
    return ErrorRecoveryManager.generate_error_report(analysis, workflow_context)