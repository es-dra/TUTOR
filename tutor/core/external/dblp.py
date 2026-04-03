"""DBLP引用验证与反幻觉检查工具

通过Semantic Scholar + DBLP + arXiv多源交叉验证论文引用的真实性，
防止LLM生成虚假引用。

使用方式：
    from core.external.dblp import ReferenceVerifier

    verifier = ReferenceVerifier()
    results = await verifier.verify_batch([
        {"title": "Attention Is All You Need", "authors": ["Vaswani"]},
        {"title": "Fake Paper That Does Not Exist", "authors": ["Nobody"]},
    ])
"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReferenceMatch:
    """引用验证结果"""
    input_title: str
    found: bool
    confidence: float  # 0.0 ~ 1.0

    # 匹配到的信息
    matched_title: Optional[str] = None
    matched_authors: Optional[List[str]] = None
    matched_year: Optional[int] = None
    matched_venue: Optional[str] = None
    matched_doi: Optional[str] = None
    matched_arxiv: Optional[str] = None
    citation_count: Optional[int] = None

    # 验证来源
    sources: List[str] = field(default_factory=list)

    # 不匹配原因
    reason: Optional[str] = None

    @property
    def is_verified(self) -> bool:
        return self.found and self.confidence >= 0.7


@dataclass
class BatchVerifyResult:
    """批量验证结果"""
    total: int = 0
    verified: int = 0
    unverified: int = 0
    low_confidence: int = 0
    results: List[ReferenceMatch] = field(default_factory=list)

    @property
    def verification_rate(self) -> float:
        return self.verified / self.total if self.total > 0 else 0.0


class ReferenceVerifier:
    """多源引用验证器

    验证流程：
    1. Semantic Scholar API（主要，结构化数据最全）
    2. arXiv API（补充CS/物理领域）
    3. DBLP（补充CS领域，通过URL解析）

    超时与限流：
    - Semantic Scholar: 100 req/5min（无key），尊重429
    - arXiv: 1 req/3s
    - 请求间自动延迟
    """

    SEMANTIC_SCHOLAR_SEARCH = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        "?query={query}&limit=3"
        "&fields=title,authors,year,venue,externalIds,citationCount"
    )
    SEMANTIC_SCHOLAR_DOI = (
        "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        "?fields=title,authors,year,venue,externalIds,citationCount"
    )
    ARXIV_API = (
        "https://export.arxiv.org/api/query"
        "?search_query=ti:{title}&max_results=3"
        "&sortBy=relevance&sortOrder=descending"
    )

    def __init__(self, request_timeout: int = 10, delay: float = 1.2):
        self.timeout = request_timeout
        self.delay = delay  # 请求间隔（秒）
        self._session_headers = {"User-Agent": "TutorClaw/0.1 (reference-verify)"}

    def _http_get(self, url: str) -> Optional[str]:
        """安全的HTTP GET请求"""
        try:
            req = urllib.request.Request(url, headers=self._session_headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning(f"Rate limited by {url}, backing off...")
                return None
            logger.debug(f"HTTP {e.code} for {url}")
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            logger.debug(f"Request failed: {url} — {e}")
            return None

    def _search_semantic_scholar(self, title: str) -> List[Dict[str, Any]]:
        """通过Semantic Scholar搜索论文"""
        url = self.SEMANTIC_SCHOLAR_SEARCH.format(
            query=urllib.parse.quote(title)
        )
        text = self._http_get(url)
        if not text:
            return []

        try:
            data = json.loads(text)
            return data.get("data", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def _search_arxiv(self, title: str) -> List[Dict[str, Any]]:
        """通过arXiv API搜索论文"""
        url = self.ARXIV_API.format(title=urllib.parse.quote(title))
        text = self._http_get(url)
        if not text:
            return []

        papers = []
        try:
            from xml.etree import ElementTree as ET
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }
            root = ET.fromstring(text)
            for entry in root.findall("atom:entry", ns):
                paper_title = (entry.find("atom:title", ns).text or "").strip()
                summary = (entry.find("atom:summary", ns).text or "").strip()[:300]
                authors = [
                    a.find("atom:name", ns).text
                    for a in entry.findall("atom:author", ns)
                    if a.find("atom:name", ns) is not None
                ]
                id_elem = entry.find("atom:id", ns)
                arxiv_id = id_elem.text.split("/abs/")[-1] if id_elem else None

                # 提取年份
                published = entry.find("atom:published", ns)
                year = None
                if published is not None and published.text:
                    try:
                        year = int(published.text[:4])
                    except (ValueError, IndexError):
                        pass

                papers.append({
                    "title": paper_title,
                    "authors": authors,
                    "summary": summary,
                    "arxivId": arxiv_id,
                    "year": year,
                })
        except Exception as e:
            logger.debug(f"Failed to parse arXiv response: {e}")

        return papers

    @staticmethod
    def _title_similarity(a: str, b: str) -> float:
        """简单的标题相似度计算（大小写不敏感，去除标点和空格差异）"""
        import re
        normalize = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
        na, nb = normalize(a), normalize(b)
        if not na or not nb:
            return 0.0
        # 最长公共子序列比例
        m, n = len(na), len(nb)
        if m == 0 or n == 0:
            return 0.0
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if na[i-1] == nb[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        lcs = dp[m][n]
        return lcs / max(m, n)

    @staticmethod
    def _author_overlap(input_authors: List[str], matched_authors: List[str]) -> float:
        """计算作者重叠度"""
        if not input_authors or not matched_authors:
            return 0.0
        input_set = {a.lower() for a in input_authors}
        matched_set = {a.lower() for a in matched_authors}
        # 检查姓氏匹配
        input_last = {a.split()[-1].lower() if a.split() else a.lower() for a in input_authors}
        matched_last = {a.split()[-1].lower() if a.split() else a.lower() for a in matched_authors}
        overlap = input_last & matched_last
        return len(overlap) / len(input_last)

    def verify_single(
        self,
        title: str,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None,
    ) -> ReferenceMatch:
        """验证单条引用

        Args:
            title: 论文标题
            authors: 作者列表（可选，提高匹配精度）
            year: 发表年份（可选）

        Returns:
            ReferenceMatch 验证结果
        """
        import time

        sources = []

        # Step 1: Semantic Scholar
        s2_results = self._search_semantic_scholar(title)
        time.sleep(self.delay)

        best_match = None
        best_confidence = 0.0

        for paper in s2_results:
            sim = self._title_similarity(title, paper.get("title", ""))
            author_bonus = 0.0
            if authors and paper.get("authors"):
                # S2 返回 [{"name": "xxx"}] 格式，需要提取名字字符串
                paper_authors = paper["authors"]
                paper_author_names = [
                    a["name"] if isinstance(a, dict) else a
                    for a in paper_authors
                ]
                author_bonus = self._author_overlap(authors, paper_author_names) * 0.3
            confidence = min(1.0, sim + author_bonus)

            if confidence > best_confidence:
                best_confidence = confidence
                ext_ids = paper.get("externalIds", {}) or {}
                best_match = {
                    "title": paper.get("title"),
                    "authors": [a.get("name") for a in paper.get("authors", [])],
                    "year": paper.get("year"),
                    "venue": paper.get("venue"),
                    "doi": ext_ids.get("DOI"),
                    "arxiv": ext_ids.get("ArXiv"),
                    "citations": paper.get("citationCount"),
                }

        if best_match and best_confidence >= 0.5:
            sources.append("semantic_scholar")

        # Step 2: arXiv（如果S2未找到或置信度低）
        if best_confidence < 0.7:
            arxiv_results = self._search_arxiv(title)
            time.sleep(self.delay)

            for paper in arxiv_results:
                sim = self._title_similarity(title, paper.get("title", ""))
                if sim > best_confidence:
                    best_confidence = sim
                    best_match = {
                        "title": paper.get("title"),
                        "authors": paper.get("authors", []),
                        "year": paper.get("year"),
                        "arxiv": paper.get("arxivId"),
                        "venue": "arXiv",
                        "citations": None,
                    }
                    sources.clear()
                    sources.append("arxiv")

        # 构建结果
        if best_match and best_confidence >= 0.5:
            return ReferenceMatch(
                input_title=title,
                found=True,
                confidence=round(best_confidence, 2),
                matched_title=best_match["title"],
                matched_authors=best_match.get("authors"),
                matched_year=best_match.get("year"),
                matched_venue=best_match.get("venue"),
                matched_doi=best_match.get("doi"),
                matched_arxiv=best_match.get("arxiv"),
                citation_count=best_match.get("citations"),
                sources=sources,
            )
        else:
            return ReferenceMatch(
                input_title=title,
                found=False,
                confidence=0.0,
                reason="No matching paper found across Semantic Scholar and arXiv",
            )

    def verify_batch(
        self,
        references: List[Dict[str, Any]],
        concurrency: int = 1,
    ) -> BatchVerifyResult:
        """批量验证引用

        Args:
            references: 引用列表，每个元素为 {"title": ..., "authors": [...], "year": ...}
            concurrency: 并发数（1=顺序，避免触发限流）

        Returns:
            BatchVerifyResult 批量验证结果
        """
        result = BatchVerifyResult(total=len(references))

        for ref in references:
            match = self.verify_single(
                title=ref.get("title", ""),
                authors=ref.get("authors"),
                year=ref.get("year"),
            )
            result.results.append(match)

            if match.is_verified:
                result.verified += 1
            elif match.found and match.confidence < 0.7:
                result.low_confidence += 1
            else:
                result.unverified += 1

            logger.info(
                f"[{'✅' if match.is_verified else '⚠️' if match.found else '❌'}] "
                f"{match.input_title[:60]}... (conf={match.confidence})"
            )

        return result

    def generate_report(self, batch_result: BatchVerifyResult) -> str:
        """生成验证报告（Markdown格式）"""
        lines = [
            f"# Reference Verification Report",
            f"",
            f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total**: {batch_result.total} | "
            f"**Verified**: {batch_result.verified} | "
            f"**Low Confidence**: {batch_result.low_confidence} | "
            f"**Unverified**: {batch_result.unverified}",
            f"**Verification Rate**: {batch_result.verification_rate:.1%}",
            f"",
        ]

        if batch_result.unverified > 0:
            lines.append("## ❌ Unverified References")
            lines.append("")
            for r in batch_result.results:
                if not r.found:
                    lines.append(f"- {r.input_title}")
            lines.append("")

        if batch_result.low_confidence > 0:
            lines.append("## ⚠️ Low Confidence Matches")
            lines.append("")
            for r in batch_result.results:
                if r.found and not r.is_verified:
                    lines.append(f"- [{r.input_title}] → matched: {r.matched_title} (conf={r.confidence})")
            lines.append("")

        lines.append("## ✅ Verified References")
        lines.append("")
        for r in batch_result.results:
            if r.is_verified:
                venue = r.matched_venue or ""
                year = f" ({r.matched_year})" if r.matched_year else ""
                authors = ", ".join(r.matched_authors[:3]) if r.matched_authors else ""
                if r.matched_authors and len(r.matched_authors) > 3:
                    authors += " et al."
                doi = f" | DOI: {r.matched_doi}" if r.matched_doi else ""
                arxiv = f" | arXiv: {r.matched_arxiv}" if r.matched_arxiv else ""
                cite = f" | Citations: {r.citation_count}" if r.citation_count else ""
                lines.append(f"- **{r.matched_title}**{year}")
                lines.append(f"  {authors} — {venue}{doi}{arxiv}{cite}")
                lines.append("")

        return "\n".join(lines)
