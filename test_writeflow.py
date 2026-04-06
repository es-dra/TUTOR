#!/usr/bin/env python3
"""
测试WriteFlow章节生成功能
"""

import logging
from pathlib import Path
from tutor.core.workflow.write import WriteFlow
from tutor.core.model import ModelGateway
from tutor.core.storage import StorageManager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_writeflow():
    """测试WriteFlow章节生成"""
    logger.info("开始测试WriteFlow章节生成功能...")
    
    try:
        # 初始化模型网关
        model_gateway = ModelGateway()
        
        # 初始化存储管理器
        storage_config = {
            "storage": {
                "database": "sqlite:///tutor.db",
                "project_dir": "./projects"
            }
        }
        storage_manager = StorageManager(storage_config)
        storage_manager.initialize()
        
        # 创建工作流配置
        config = {
            "output_format": "markdown",
            "expert_review": False  # MVP模式
        }
        
        # 创建工作流实例
        writeflow = WriteFlow(
            model_gateway=model_gateway,
            storage_manager=storage_manager,
            config=config
        )
        
        # 准备测试数据
        test_context = {
            "topic": "动态自适应思维链框架",
            "description": "开发一个根据问题复杂度自动调整推理深度的思维链框架，提高AI模型在复杂任务上的表现。",
            "experiment_summary": {
                "title": "动态思维链框架实验",
                "metrics": {
                    "accuracy": 0.85,
                    "efficiency": 0.92,
                    "robustness": 0.78
                },
                "conclusion": "实验结果表明，动态自适应思维链框架在复杂数学推理和代码生成任务上表现优异，相比传统方法提升了15%的准确率。"
            }
        }
        
        # 执行工作流
        logger.info("执行WriteFlow工作流...")
        result = writeflow.run(test_context)
        
        # 输出结果
        logger.info("WriteFlow执行完成！")
        logger.info(f"总章节数: {result.get('polished_sections', {}).get('total_sections', 0)}")
        logger.info(f"总词数: {result.get('final_export', {}).get('total_words', 0)}")
        
        # 打印生成的章节
        if 'draft_sections' in result:
            logger.info("\n生成的章节:")
            for section_title, section_data in result['draft_sections'].items():
                logger.info(f"\n=== {section_title} ===")
                logger.info(f"词数: {section_data.get('word_count', 0)}")
                logger.info(f"内容预览: {section_data.get('content', '')[:100]}...")
        
        # 打印最终论文文件路径
        if 'final_export' in result and 'paper_file' in result['final_export']:
            logger.info(f"\n最终论文保存位置: {result['final_export']['paper_file']}")
        
        return True
        
    except Exception as e:
        logger.error(f"WriteFlow测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_writeflow()
    if success:
        logger.info("WriteFlow章节生成测试成功！")
    else:
        logger.error("WriteFlow章节生成测试失败！")
