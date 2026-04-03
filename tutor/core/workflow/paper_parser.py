"""论文解析器 - 支持PDF和arXiv URL

MVP 实现：
- PDF文本提取
- arXiv URL处理
- 文件存在性验证
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urlparse

import requests
from io import BytesIO

logger = logging.getLogger(__name__)


@dataclass
class PaperMetadata:
    """论文元数据"""
    title: str
    authors: List[str]
    abstract: str
    source: str  # 'file' or 'arxiv'
    file_path: Optional[Path] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None
    raw_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于检查点保存）"""
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "source": self.source,
            "file_path": str(self.file_path) if self.file_path else None,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "raw_text": self.raw_text,  # 保存完整文本用于检查点恢复
            "raw_text_length": len(self.raw_text)
        }


class PaperParser(ABC):
    """论文解析器抽象基类"""
    
    @abstractmethod
    def parse(self, source: Union[str, Path, BytesIO]) -> PaperMetadata:
        """解析论文
        
        Args:
            source: 论文来源（文件路径、URL或字节流）
            
        Returns:
            论文元数据
        """
        pass
    
    @abstractmethod
    def can_handle(self, source: Union[str, Path, BytesIO]) -> bool:
        """判断是否可以处理该来源"""
        pass


class PDFParser(PaperParser):
    """PDF文件解析器
    
    MVP: 使用PyPDF2进行简单文本提取
    后续优化: 支持更多格式、更好的文本提取
    """
    
    def __init__(self):
        self._pdf = None
    
    def can_handle(self, source: Union[str, Path, BytesIO]) -> bool:
        """检查是否为PDF"""
        if isinstance(source, (str, Path)):
            path = Path(source)
            return path.exists() and path.suffix.lower() == '.pdf'
        elif isinstance(source, BytesIO):
            # 检查前4个字节是否为PDF魔数
            current = source.tell()
            header = source.read(4)
            source.seek(current)
            return header == b'%PDF'
        return False
    
    def parse(self, source: Union[str, Path, BytesIO]) -> PaperMetadata:
        """解析PDF"""
        try:
            pdf_file = self._open_pdf(source)
            
            # 提取文本
            text = self._extract_text(pdf_file)
            
            # 提取元数据
            metadata = self._extract_metadata(pdf_file, text)
            
            # 提取摘要
            abstract = self._extract_abstract(text)
            
            return PaperMetadata(
                title=metadata.get("title", "Unknown Title"),
                authors=metadata.get("authors", []),
                abstract=abstract,
                source="file",
                file_path=Path(source) if isinstance(source, (str, Path)) else None,
                raw_text=text
            )
            
        except Exception as e:
            logger.error(f"PDF parsing failed: {e}")
            raise PaperParseError(f"Failed to parse PDF: {e}")
        finally:
            self._close_pdf()
    
    def _open_pdf(self, source: Union[str, Path, BytesIO]):
        """打开PDF文件"""
        try:
            import PyPDF2
        except ImportError:
            raise PaperParseError("PyPDF2 not installed. Install with: pip install PyPDF2")
        
        if isinstance(source, (str, Path)):
            file_path = Path(source)
            if not file_path.exists():
                raise FileNotFoundError(f"PDF file not found: {file_path}")
            self._pdf = PyPDF2.PdfReader(open(file_path, 'rb'))
        elif isinstance(source, BytesIO):
            self._pdf = PyPDF2.PdfReader(source)
        else:
            raise ValueError(f"Unsupported source type: {type(source)}")
            
        return self._pdf
    
    def _close_pdf(self):
        """关闭PDF文件"""
        if self._pdf:
            self._pdf.stream.close() if hasattr(self._pdf, 'stream') else None
            self._pdf = None
    
    def _extract_text(self, pdf_reader) -> str:
        """提取所有文本"""
        text_parts = []
        for page in pdf_reader.pages:
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"Failed to extract text from page: {e}")
                continue
        return "\n".join(text_parts)
    
    def _extract_metadata(self, pdf_reader, text: str) -> Dict[str, Any]:
        """提取元数据"""
        metadata = {"title": None, "authors": []}
        
        # 尝试从PDF元数据提取
        if pdf_reader.metadata:
            metadata["title"] = pdf_reader.metadata.get('/Title', None)
            author_str = pdf_reader.metadata.get('/Author', None)
            if author_str:
                metadata["authors"] = [a.strip() for a in str(author_str).split(',')]
        
        # 如果元数据不完整，从前几行文本推测
        if not metadata["title"]:
            title = self._guess_title(text)
            if title:
                metadata["title"] = title
        
        return metadata
    
    def _guess_title(self, text: str, max_lines: int = 5) -> Optional[str]:
        """从前几行文本猜测标题"""
        lines = text.split('\n')[:max_lines]
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 200:
                # 避免太短或太长的行
                if not re.match(r'^\d+$', line) and not re.match(r'^[a-z]+$', line):
                    return line
        return None
    
    def _extract_abstract(self, text: str) -> str:
        """提取摘要"""
        # 查找"Abstract"或"摘要"部分
        patterns = [
            r'(?i)Abstract\s*\n\s*(.*?)(?=\n\s*(?:1\.|Introduction|Keywords|\n\s*$))',
            r'(?i)摘要\s*\n\s*(.*?)(?=\n\s*(?:一、|引言|关键词|\n\s*$))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                # 清理多余空白
                abstract = re.sub(r'\s+', ' ', abstract)
                return abstract[:1000]  # 限制长度
        
        # 未找到摘要，返回空
        return ""


class ArXivParser(PaperParser):
    """arXiv URL解析器

    MVP: 从arXiv下载PDF并解析
    注意: 需要网络连接
    """

    # arXiv URL模式
    ARXIV_URL_PATTERN = re.compile(
        r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})',
        re.IGNORECASE
    )

    # arXiv abstract HTML URL模板
    ABSTRACT_URL_TEMPLATE = "https://arxiv.org/abs/{arxiv_id}"

    # arXiv PDF URL模板
    PDF_URL_TEMPLATE = "https://arxiv.org/pdf/{arxiv_id}.pdf"

    def can_handle(self, source: Union[str, Path, BytesIO]) -> bool:
        """检查是否为arXiv URL"""
        if isinstance(source, (str, Path)):
            url = str(source)
            return bool(self.ARXIV_URL_PATTERN.search(url))
        return False

    def parse(self, source: Union[str, Path, BytesIO]) -> PaperMetadata:
        """解析arXiv论文

        策略:
        1. 先获取HTML abstract页面提取标题、作者、摘要（更可靠）
        2. 然后下载PDF提取正文
        """
        if not isinstance(source, (str, Path)):
            raise ValueError("arXiv parser only supports URL strings")

        url = str(source)
        match = self.ARXIV_URL_PATTERN.search(url)
        if not match:
            raise ValueError(f"Invalid arXiv URL: {url}")

        arxiv_id = match.group(1)
        abstract_url = self.ABSTRACT_URL_TEMPLATE.format(arxiv_id=arxiv_id)
        pdf_url = self.PDF_URL_TEMPLATE.format(arxiv_id=arxiv_id)

        logger.info(f"Parsing arXiv paper: {arxiv_id}")

        try:
            # Step 1: 获取HTML abstract页面提取元数据
            metadata = self._fetch_abstract_metadata(arxiv_id, abstract_url)

            # Step 2: 下载PDF获取正文
            pdf_text = self._fetch_pdf_text(pdf_url)
            metadata.raw_text = pdf_text if pdf_text else metadata.raw_text

            # 确保有足够的文本
            if not metadata.raw_text or len(metadata.raw_text) < 100:
                # 如果PDF文本太短，尝试从abstract构建基本文本
                metadata.raw_text = f"{metadata.title}\n\n{metadata.abstract}"

            # 补充arXiv信息
            metadata.arxiv_id = arxiv_id
            metadata.source = "arxiv"
            metadata.url = f"https://arxiv.org/abs/{arxiv_id}"

            return metadata

        except requests.RequestException as e:
            logger.error(f"Failed to fetch arXiv paper: {e}")
            raise PaperParseError(f"Failed to fetch from arXiv: {e}")
        except Exception as e:
            logger.error(f"arXiv parsing failed: {e}")
            raise

    def _fetch_abstract_metadata(self, arxiv_id: str, abstract_url: str) -> PaperMetadata:
        """从HTML abstract页面提取元数据"""
        logger.info(f"Fetching abstract metadata from: {abstract_url}")

        response = requests.get(abstract_url, timeout=30)
        response.raise_for_status()

        html_content = response.text

        # 提取标题
        title = self._extract_title(html_content)
        # 提取作者
        authors = self._extract_authors(html_content)
        # 提取摘要
        abstract = self._extract_abstract(html_content)

        logger.info(f"Extracted metadata: title={title[:50]}, authors={len(authors)}, abstract_len={len(abstract)}")

        return PaperMetadata(
            title=title or "Unknown Title",
            authors=authors,
            abstract=abstract,
            source="arxiv",
            arxiv_id=arxiv_id,
            url=abstract_url,
            raw_text=f"{title}\n\n{' '.join(authors)}\n\n{abstract}",  # 临时文本，后续会被PDF内容替换
        )

    def _extract_title(self, html: str) -> str:
        """从HTML提取标题"""
        import re
        # 常见模式: <h1 class="title">...</h1> 或 <div class="title">...</div>
        patterns = [
            r'<h1[^>]*class="title"[^>]*>(.*?)</h1>',
            r'<div[^>]*class="title"[^>]*>(.*?)</div>',
            r'<meta[^>]*name="citation_title"[^>]*content="([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # 清理HTML标签
                title = re.sub(r'<[^>]+>', '', title)
                title = re.sub(r'\s+', ' ', title).strip()
                if title:
                    return title
        return ""

    def _extract_authors(self, html: str) -> List[str]:
        """从HTML提取作者列表"""
        import re
        authors = []
        # 模式: <div class="authors">...</div> 或 <meta name="citation_author">
        author_section = re.search(r'<div[^>]*class="authors"[^>]*>(.*?)</div>', html, re.DOTALL)
        if author_section:
            author_html = author_section.group(1)
            # 提取每个作者
            name_patterns = [
                r'<a[^>]*>([^<]+)</a>',
                r'<span[^>]*>([^<]+)</span>',
            ]
            for pattern in name_patterns:
                matches = re.findall(pattern, author_html)
                for name in matches:
                    name = name.strip()
                    if name and len(name) > 2:
                        authors.append(name)
        # 备选：meta标签
        if not authors:
            meta_authors = re.findall(r'<meta[^>]*name="citation_author"[^>]*content="([^"]+)"', html)
            authors = [a.strip() for a in meta_authors if a.strip()]
        return authors[:20]  # 限制数量

    def _extract_abstract(self, html: str) -> str:
        """从HTML提取摘要"""
        import re
        # 摘要通常在 <blockquote class="abstract"> 或 <div class="abstract">
        patterns = [
            r'<blockquote[^>]*class="abstract"[^>]*>(.*?)</blockquote>',
            r'<div[^>]*class="abstract"[^>]*>(.*?)</div>',
            r'<meta[^>]*name="citation_abstract"[^>]*content="([^"]+)"',
            r'Abstract:\s*(.*?)(?:\n\n|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                abstract = match.group(1).strip()
                # 清理HTML标签
                abstract = re.sub(r'<[^>]+>', '', abstract)
                abstract = re.sub(r'\s+', ' ', abstract).strip()
                # 移除 "Abstract." 前缀
                abstract = re.sub(r'^Abstract\.?\s*', '', abstract, flags=re.IGNORECASE)
                if abstract:
                    return abstract[:2000]  # 限制长度
        return ""

    def _fetch_pdf_text(self, pdf_url: str) -> str:
        """从PDF提取正文文本

        Returns:
            提取的正文文本，如果提取失败或质量差则返回空字符串
        """
        logger.info(f"Fetching PDF from: {pdf_url}")
        try:
            response = requests.get(pdf_url, timeout=60)
            response.raise_for_status()

            pdf_bytes = BytesIO(response.content)
            pdf_parser = PDFParser()
            metadata = pdf_parser.parse(pdf_bytes)

            # 如果提取的文本太短，返回空
            if not metadata.raw_text or len(metadata.raw_text) < 500:
                logger.warning(f"PDF text too short: {len(metadata.raw_text) if metadata.raw_text else 0} chars")
                return ""

            # 检查是否以垃圾内容开头（常见于arXiv的第一页）
            first_200 = metadata.raw_text[:200].lower()
            garbage_phrases = ['provided proper attribution', 'google hereby grants', 'ccby license',
                             'creative commons', 'copyright notice', 'journalistic or scholarly']
            starts_with_garbage = any(gp in first_200 for gp in garbage_phrases)

            # 检查是否包含常见的研究论文关键词
            text_lower = metadata.raw_text.lower()
            research_keywords = ['introduction', 'method', 'experiment', 'result', 'conclusion', 'abstract']
            keyword_count = sum(1 for kw in research_keywords if kw in text_lower)

            # 如果开头是垃圾内容，或者关键词太少，返回空让abstract成为主要内容
            if starts_with_garbage:
                logger.warning(f"PDF starts with garbage content, skipping PDF text")
                return ""
            if keyword_count < 3:
                logger.warning(f"PDF content appears poor (only {keyword_count} research keywords found)")
                return ""

            # 检查标题是否出现在文本前1000字符内
            if metadata.title and metadata.title in metadata.raw_text[:1000]:
                logger.info(f"PDF parsed successfully: {len(metadata.raw_text)} chars, {keyword_count} research keywords")
            else:
                # 标题不在前1000字符，可能内容偏移但仍使用
                logger.warning(f"PDF title not near start, content may include prepend")

            return metadata.raw_text
        except Exception as e:
            logger.warning(f"PDF fetch/parse failed: {e}")
            return ""

    def extract_arxiv_id(self, url: str) -> Optional[str]:
        """从URL提取arXiv ID"""
        match = self.ARXIV_URL_PATTERN.search(url)
        return match.group(1) if match else None


class SmartPaperParser:
    """智能论文解析器
    
    自动选择合适的解析器处理输入。
    """
    
    def __init__(self):
        self.parsers: List[PaperParser] = [
            ArXivParser(),
            PDFParser(),
        ]
    
    def parse(self, source: Union[str, Path, BytesIO]) -> PaperMetadata:
        """解析论文
        
        Args:
            source: 论文来源（文件路径、URL或字节流）
            
        Returns:
            论文元数据
            
        Raises:
            FileNotFoundError: 文件不存在
            PaperParseError: 解析失败
        """
        # 查找合适的解析器
        parser = self._find_parser(source)
        if not parser:
            raise PaperParseError(f"No suitable parser for source: {source}")
        
        logger.info(f"Using parser: {parser.__class__.__name__}")
        return parser.parse(source)
    
    def can_parse(self, source: Union[str, Path, BytesIO]) -> bool:
        """检查是否可以解析"""
        parser = self._find_parser(source)
        return parser is not None
    
    def _find_parser(self, source: Union[str, Path, BytesIO]) -> Optional[PaperParser]:
        """查找合适的解析器"""
        for parser in self.parsers:
            if parser.can_handle(source):
                return parser
        return None
    
    def register_parser(self, parser: PaperParser) -> None:
        """注册自定义解析器"""
        self.parsers.insert(0, parser)


class PaperParseError(Exception):
    """论文解析异常"""
    pass


# 便捷函数
def parse_paper(source: Union[str, Path, BytesIO]) -> PaperMetadata:
    """便捷函数：解析论文"""
    parser = SmartPaperParser()
    return parser.parse(source)


def is_supported(source: Union[str, Path, BytesIO]) -> bool:
    """便捷函数：检查是否支持"""
    parser = SmartPaperParser()
    return parser.can_parse(source)


__all__ = [
    'PaperMetadata',
    'PaperParser',
    'PDFParser',
    'ArXivParser',
    'SmartPaperParser',
    'PaperParseError',
    'parse_paper',
    'is_supported',
]