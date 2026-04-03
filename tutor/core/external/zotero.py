"""Zotero集成模块

与Zotero文献管理库交互，支持：
- 搜索库中文献
- 添加新文献
- 获取集合（collections）
- 导出引用（BibTeX格式）

使用Zotero Web API v3：
https://www.zotero.org/support/dev/web_api/v3/start

使用方式：
    from core.external.zotero import ZoteroClient

    client = ZoteroClient(
        api_key="your-api-key",
        library_id="123456",
        library_type="user",
    )
    items = client.search_items("machine learning")
    bib = client.export_bibtex(items[0]["key"])
"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ZoteroAPIError(Exception):
    """Zotero API错误"""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class ZoteroClient:
    """Zotero Web API v3 客户端

    支持用户库和群组库。
    """

    BASE_URL = "https://api.zotero.org"
    ITEMS_PER_PAGE = 25

    def __init__(
        self,
        api_key: Optional[str] = None,
        library_id: Optional[str] = None,
        library_type: str = "user",
        timeout: int = 15,
    ):
        self.api_key = api_key
        self.library_id = library_id
        self.library_type = library_type  # "user" or "group"
        self.timeout = timeout
        self._total_requests = 0

    @property
    def is_configured(self) -> bool:
        """检查API是否已配置"""
        return bool(self.api_key and self.library_id)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Zotero-Api-Key": self.api_key or "",
            "Zotero-Api-Version": "3",
            "Accept": "application/json",
        }
        return headers

    def _build_url(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        base = f"{self.BASE_URL}/{self.library_type}s/{self.library_id}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            base += f"?{query}"
        return base

    def _request(self, path: str, method: str = "GET",
                 params: Optional[Dict[str, str]] = None,
                 data: Optional[bytes] = None) -> Any:
        """执行API请求"""
        if not self.is_configured:
            raise ZoteroAPIError("Zotero API not configured. Set api_key and library_id.")

        url = self._build_url(path, params)
        req = urllib.request.Request(url, headers=self._get_headers(), method=method)
        if data:
            req.data = data
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._total_requests += 1
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise ZoteroAPIError(f"HTTP {e.code}: {body}", status_code=e.code)
        except urllib.error.URLError as e:
            raise ZoteroAPIError(f"Connection error: {e}")
        except TimeoutError:
            raise ZoteroAPIError("Request timed out")

    def search_items(
        self,
        query: str,
        item_type: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """搜索文献

        Args:
            query: 搜索关键词（标题、作者、标签）
            item_type: 文献类型过滤（journalArticle, book 等）
            limit: 返回数量上限

        Returns:
            文献条目列表
        """
        params: Dict[str, str] = {
            "q": query,
            "limit": str(min(limit, self.ITEMS_PER_PAGE)),
            "format": "json",
        }
        if item_type:
            params["itemType"] = item_type

        results = self._request("/items", params=params)

        if not isinstance(results, list):
            return []

        # Filter out attachments/notes, keep only actual items
        items = [item for item in results if item.get("data", {}).get("itemType") not in
                 ("attachment", "note")]
        return items

    def get_item(self, item_key: str) -> Dict[str, Any]:
        """获取单个文献详情"""
        return self._request(f"/items/{item_key}", params={"format": "json"})

    def get_collections(self) -> List[Dict[str, Any]]:
        """获取所有集合"""
        results = self._request("/collections", params={"format": "json"})
        return results if isinstance(results, list) else []

    def get_collection_items(self, collection_key: str, limit: int = 25) -> List[Dict[str, Any]]:
        """获取集合中的文献"""
        params = {"limit": str(min(limit, self.ITEMS_PER_PAGE)), "format": "json"}
        results = self._request(f"/collections/{collection_key}/items", params=params)
        return [i for i in (results if isinstance(results, list) else [])
                if i.get("data", {}).get("itemType") not in ("attachment", "note")]

    def export_bibtex(self, item_key: str) -> str:
        """导出单条文献为BibTeX格式"""
        url = self._build_url(f"/items/{item_key}", params={"format": "bibtex"})
        req = urllib.request.Request(url, headers=self._get_headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._total_requests += 1
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            raise ZoteroAPIError(f"Failed to export BibTeX: {e}")

    def export_multiple_bibtex(self, item_keys: List[str]) -> str:
        """批量导出BibTeX"""
        entries = []
        for key in item_keys:
            try:
                bib = self.export_bibtex(key)
                entries.append(bib.strip())
            except ZoteroAPIError as e:
                logger.warning(f"Failed to export {key}: {e}")
        return "\n\n".join(entries)

    def create_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新文献条目

        Args:
            item_data: 符合Zotero API格式的文献数据

        Returns:
            创建的文献条目
        """
        payload = json.dumps([item_data]).encode("utf-8")
        return self._request("/items", method="POST", data=payload)

    def get_stats(self) -> Dict[str, Any]:
        """获取库统计信息"""
        items = self._request("/items", params={"limit": "1", "format": "json"})
        total = 0
        if isinstance(items, list):
            total = items[0].get("library", {}).get("numItems", 0) if items else 0

        return {
            "library_id": self.library_id,
            "library_type": self.library_type,
            "total_items": total,
            "total_requests": self._total_requests,
        }

    def format_item_summary(self, item: Dict[str, Any]) -> str:
        """格式化文献摘要（便于展示）"""
        data = item.get("data", {})
        creators = data.get("creators", [])
        authors = ", ".join(
            c.get("lastName", "") + " " + c.get("firstName", "")[:1] + "."
            for c in creators[:3] if c.get("creatorType") == "author"
        )
        if len(creators) > 3:
            authors += " et al."

        title = data.get("title", "Untitled")
        item_type = data.get("itemType", "unknown")
        date = data.get("date", "")
        key = data.get("key", "")
        doi = data.get("DOI", "")
        journal = data.get("publicationTitle", "")

        parts = [f"**{title}**"]
        if authors:
            parts[0] += f" — {authors}"
        if date:
            parts[0] += f" ({date})"
        if journal:
            parts[0] += f" — *{journal}*"

        parts.append(f"Type: {item_type} | Key: {key}")
        if doi:
            parts.append(f"DOI: {doi}")

        return "\n".join(parts)

    def search_and_format(self, query: str, limit: int = 5) -> str:
        """搜索并格式化结果（便捷方法）"""
        items = self.search_items(query, limit=limit)
        if not items:
            return f"No results found for '{query}'"

        lines = [f"Found {len(items)} results for '{query}':\n"]
        for item in items:
            lines.append(self.format_item_summary(item))
            lines.append("")
        return "\n".join(lines)
