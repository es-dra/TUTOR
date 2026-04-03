"""文献加载步骤 - IdeaFlow 第一步

功能：
- 加载PDF文件或从arXiv获取论文
- 提取文本内容
- 验证文件存在性
- 生成清晰的错误信息
"""

import logging
from pathlib import Path
from typing import Dict, Any, List

from tutor.core.workflow import WorkflowStep, WorkflowContext
from tutor.core.workflow.paper_parser import SmartPaperParser, PaperMetadata, PaperParseError

logger = logging.getLogger(__name__)


class PaperLoadingStep(WorkflowStep):
    """文献加载步骤
    
    从用户提供的文献列表加载论文内容。
    支持：
    - 本地PDF文件路径
    - arXiv URL（自动下载）
    - PDF字节流（通过上下文传递）
    
    状态输出：
    - papers: List[PaperMetadata] - 已加载的论文列表
    - load_errors: List[Dict] - 加载错误列表
    """
    
    def __init__(self):
        super().__init__(
            name="paper_loading",
            description="Load papers from user-provided sources (PDF files or arXiv URLs)"
        )
        self.parser = SmartPaperParser()
    
    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行文献加载
        
        从上下文中获取文献列表，并解析每个文献源。
        
        Args:
            context: 工作流上下文，应包含：
                - paper_sources: List[str] - 文献源路径/URL列表
                
        Returns:
            {
                "papers": [PaperMetadata, ...],
                "load_errors": [{"source": str, "error": str}, ...],
                "total_loaded": int,
                "total_failed": int
            }
        """
        # 获取文献源列表
        paper_sources = context.get_state("paper_sources", [])
        
        if not paper_sources:
            # 尝试从配置读取
            config_sources = context.config.get("paper_sources", [])
            if config_sources:
                paper_sources = config_sources
            else:
                raise ValueError(
                    "No paper sources provided. Set 'paper_sources' in config "
                    "or context state before running this step."
                )
        
        logger.info(f"Loading {len(paper_sources)} papers")
        
        papers: List[PaperMetadata] = []
        load_errors: List[Dict[str, str]] = []
        
        for i, source in enumerate(paper_sources, 1):
            logger.info(f"Processing paper {i}/{len(paper_sources)}: {source}")

            try:
                # 检查是否为 URL（跳过文件存在性检查）
                source_str = str(source)
                is_url = source_str.startswith('http://') or source_str.startswith('https://')

                # 如果不是 URL，检查本地文件是否存在
                if not is_url and isinstance(source, (str, Path)):
                    source_path = Path(source)
                    if not source_path.exists() and not source_path.is_absolute():
                        # 尝试相对配置根目录
                        config_root = context.storage_path.parent.parent / "config"
                        alt_path = config_root / source
                        if alt_path.exists():
                            source_path = alt_path

                    if not source_path.exists():
                        raise FileNotFoundError(f"File not found: {source_path}")

                # 解析论文
                metadata = self.parser.parse(source)
                papers.append(metadata)
                
                logger.info(f"✓ Loaded: {metadata.title} "
                          f"({len(metadata.raw_text)} chars, "
                          f"{len(metadata.authors)} authors)")
                
            except PaperParseError as e:
                error_msg = str(e)
                logger.warning(f"✗ Failed to parse {source}: {error_msg}")
                load_errors.append({"source": str(source), "error": error_msg})
                
            except Exception as e:
                error_msg = f"Unexpected error: {type(e).__name__}: {e}"
                logger.warning(f"✗ Failed to load {source}: {error_msg}", exc_info=True)
                load_errors.append({"source": str(source), "error": error_msg})
        
        # 更新上下文状态
        context.set_state("papers", papers)
        context.set_state("load_errors", load_errors)
        
        result = {
            "papers": [p.to_dict() for p in papers],
            "load_errors": load_errors,
            "total_loaded": len(papers),
            "total_failed": len(load_errors),
            "all_sources": paper_sources
        }
        
        logger.info(
            f"Paper loading completed: {len(papers)} loaded, "
            f"{len(load_errors)} failed"
        )
        
        return result
    
    def validate(self, context: WorkflowContext) -> List[str]:
        """验证前置条件"""
        errors = []
        
        # 检查是否有文献源
        paper_sources = context.get_state("paper_sources")
        config_sources = context.config.get("paper_sources", [])
        
        if not paper_sources and not config_sources:
            errors.append(
                "No paper sources provided. Please provide 'paper_sources' "
                "as a list of file paths or arXiv URLs."
            )
        
        # 检查PyPDF2是否可用
        try:
            import PyPDF2
        except ImportError:
            errors.append(
                "PyPDF2 not installed. Install with: pip install PyPDF2"
            )
        
        return errors
    
    def rollback(self, context: WorkflowContext) -> None:
        """回滚：清理已加载的论文状态"""
        context.set_state("papers", [])
        context.set_state("load_errors", [])
        self.logger.info("Rolled back paper loading step")


class PaperValidationStep(WorkflowStep):
    """文献验证步骤
    
    验证加载的论文质量：
    - 检查文本长度
    - 检测是否为空文件
    - 验证必要字段
    
    状态输出：
    - validated_papers: List[PaperMetadata] - 通过验证的论文
    - validation_errors: List[Dict] - 验证错误
    """
    
    def __init__(self,
                 min_text_length: int = 1000,
                 require_abstract: bool = True):
        super().__init__(
            name="paper_validation",
            description="Validate loaded papers for quality and completeness"
        )
        self.min_text_length = min_text_length
        self.require_abstract = require_abstract
    
    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """执行验证
        
        Args:
            context: 应包含 'papers' 状态
            
        Returns:
            {
                "validated_papers": [PaperMetadata, ...],
                "validation_errors": [{"paper_index": int, "error": str}, ...],
                "total_valid": int,
                "total_invalid": int
            }
        """
        papers = context.get_state("papers", [])
        
        if not papers:
            raise ValueError(
                "No papers to validate. Please run paper_loading step first."
            )
        
        validated_papers: List[PaperMetadata] = []
        validation_errors: List[Dict[str, Any]] = []
        
        for idx, paper in enumerate(papers):
            errors = []

            # Handle both dict (from checkpoint) and PaperMetadata (direct)
            if isinstance(paper, dict):
                raw_text = paper.get('raw_text', '')
                title = paper.get('title', '')
                abstract = paper.get('abstract')
            else:
                raw_text = paper.raw_text
                title = paper.title
                abstract = paper.abstract

            # 检查文本长度
            if len(raw_text) < self.min_text_length:
                errors.append(
                    f"Text too short: {len(raw_text)} chars "
                    f"(min: {self.min_text_length})"
                )

            # 检查标题
            if not title or title == "Unknown Title":
                errors.append("Missing or unknown title")

            # 检查摘要
            if self.require_abstract and not abstract:
                errors.append("Missing abstract")
            
            if errors:
                validation_errors.append({
                    "paper_index": idx,
                    "title": title,
                    "errors": errors
                })
                logger.warning(f"Paper validation failed [{idx}]: {title} - {errors}")
            else:
                validated_papers.append(paper)
                logger.info(f"Paper validated [{idx}]: {title}")
        
        # 更新上下文
        context.set_state("validated_papers", validated_papers)
        context.set_state("validation_errors", validation_errors)
        
        # Convert papers to dicts for result (handle both dict and PaperMetadata)
        validated_papers_dicts = []
        for p in validated_papers:
            if isinstance(p, dict):
                validated_papers_dicts.append(p)
            else:
                validated_papers_dicts.append(p.to_dict())

        result = {
            "validated_papers": validated_papers_dicts,
            "validation_errors": validation_errors,
            "total_valid": len(validated_papers),
            "total_invalid": len(validation_errors)
        }
        
        logger.info(
            f"Paper validation completed: {len(validated_papers)} valid, "
            f"{len(validation_errors)} invalid"
        )
        
        return result
    
    def validate(self, context: WorkflowContext) -> List[str]:
        """验证前置条件"""
        errors = []
        papers = context.get_state("papers", [])
        
        if not papers:
            errors.append("No papers to validate. Run paper_loading first.")
        
        return errors


__all__ = [
    'PaperLoadingStep',
    'PaperValidationStep',
]