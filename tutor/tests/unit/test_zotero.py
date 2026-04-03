"""ZoteroClient 单元测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tutor.core.external.zotero import (
    ZoteroClient,
    ZoteroAPIError,
)


# --- Fixtures ---

@pytest.fixture
def client():
    return ZoteroClient(
        api_key="test-key-123",
        library_id="12345",
        library_type="user",
    )


@pytest.fixture
def sample_item():
    return {
        "key": "ABCD1234",
        "data": {
            "key": "ABCD1234",
            "itemType": "journalArticle",
            "title": "Attention Is All You Need",
            "creators": [
                {"creatorType": "author", "firstName": "Ashish", "lastName": "Vaswani"},
                {"creatorType": "author", "firstName": "Noam", "lastName": "Shazeer"},
            ],
            "date": "2017",
            "DOI": "10.48550/arXiv.1706.03762",
            "publicationTitle": "NeurIPS",
        }
    }


@pytest.fixture
def sample_items():
    return [
        {
            "key": "ITEM1",
            "data": {
                "key": "ITEM1",
                "itemType": "journalArticle",
                "title": "Paper A",
                "creators": [{"creatorType": "author", "firstName": "A", "lastName": "Author"}],
                "date": "2024",
            }
        },
        {
            "key": "ATTACH1",
            "data": {"key": "ATTACH1", "itemType": "attachment", "title": "PDF"},
        },
        {
            "key": "NOTE1",
            "data": {"key": "NOTE1", "itemType": "note"},
        },
    ]


# --- ZoteroClient Configuration Tests ---

class TestConfiguration:
    def test_configured(self, client):
        assert client.is_configured is True

    def test_not_configured(self):
        c = ZoteroClient()
        assert c.is_configured is False

    def test_configured_no_key(self):
        c = ZoteroClient(library_id="12345")
        assert c.is_configured is False


# --- URL Building Tests ---

class TestURLBuilding:
    def test_basic_url(self, client):
        url = client._build_url("/items")
        assert "api.zotero.org" in url
        assert "/users/12345/items" in url

    def test_url_with_params(self, client):
        url = client._build_url("/items", {"q": "test", "limit": "5"})
        assert "q=test" in url
        assert "limit=5" in url

    def test_group_library_url(self):
        c = ZoteroClient(api_key="k", library_id="999", library_type="group")
        url = c._build_url("/items")
        assert "/groups/999/items" in url


# --- Headers Tests ---

class TestHeaders:
    def test_headers_include_key(self, client):
        headers = client._get_headers()
        assert headers["Zotero-Api-Key"] == "test-key-123"
        assert headers["Zotero-Api-Version"] == "3"


# --- Search Tests ---

class TestSearchItems:
    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_search(self, mock_request, client, sample_items):
        mock_request.return_value = sample_items
        results = client.search_items("attention")
        assert len(results) == 1  # attachments/notes filtered out
        assert results[0]["key"] == "ITEM1"

    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_search_empty(self, mock_request, client):
        mock_request.return_value = []
        results = client.search_items("nonexistent")
        assert results == []

    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_search_with_type_filter(self, mock_request, client):
        mock_request.return_value = []
        client.search_items("test", item_type="book")
        args, kwargs = mock_request.call_args
        # params 在 kwargs 里，检查 itemType 参数
        assert kwargs["params"]["itemType"] == "book"

    def test_not_configured_raises(self):
        client = ZoteroClient()
        with pytest.raises(ZoteroAPIError, match="not configured"):
            client.search_items("test")


# --- Item Tests ---

class TestGetItem:
    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_get_item(self, mock_request, client, sample_item):
        mock_request.return_value = sample_item
        result = client.get_item("ABCD1234")
        assert result["data"]["title"] == "Attention Is All You Need"


# --- Collection Tests ---

class TestCollections:
    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_get_collections(self, mock_request, client):
        mock_request.return_value = [
            {"key": "C1", "data": {"name": "Machine Learning"}},
        ]
        cols = client.get_collections()
        assert len(cols) == 1
        assert cols[0]["data"]["name"] == "Machine Learning"

    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_collection_items(self, mock_request, client, sample_items):
        mock_request.return_value = sample_items
        items = client.get_collection_items("C1")
        assert len(items) == 1  # filtered


# --- BibTeX Export Tests ---

class TestBibTeXExport:
    @patch("urllib.request.urlopen")
    def test_export_bibtex(self, mock_urlopen, client):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"@article{vaswani2017, title={Attention}}"
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_resp

        bib = client.export_bibtex("ABCD1234")
        assert "Attention" in bib

    @patch("urllib.request.urlopen")
    def test_export_multiple(self, mock_urlopen, client):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"@article{key1, title={A}}"
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_resp

        bib = client.export_multiple_bibtex(["K1", "K2"])
        assert "@article" in bib


# --- Create Item Tests ---

class TestCreateItem:
    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_create_item(self, mock_request, client):
        mock_request.return_value = {"successful": {"0": True}}
        item_data = {
            "itemType": "journalArticle",
            "title": "New Paper",
        }
        result = client.create_item(item_data)
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert kwargs.get("method") == "POST"


# --- Format Tests ---

class TestFormatSummary:
    def test_format_full(self, client, sample_item):
        summary = client.format_item_summary(sample_item)
        assert "Attention Is All You Need" in summary
        assert "Vaswani" in summary
        assert "2017" in summary
        assert "NeurIPS" in summary
        assert "ABCD1234" in summary

    def test_format_minimal(self, client):
        item = {"data": {"itemType": "book", "title": "Some Book", "key": "B1"}}
        summary = client.format_item_summary(item)
        assert "Some Book" in summary

    def test_search_and_format(self, client, sample_items):
        with patch.object(client, "search_items", return_value=[sample_items[0]]):
            result = client.search_and_format("test")
            assert "Paper A" in result

    def test_search_and_format_empty(self, client):
        with patch.object(client, "search_items", return_value=[]):
            result = client.search_and_format("nothing")
            assert "No results" in result


# --- Stats Tests ---

class TestStats:
    @patch("tutor.core.external.zotero.ZoteroClient._request")
    def test_stats(self, mock_request, client):
        mock_request.return_value = [{"library": {"numItems": 42}}]
        stats = client.get_stats()
        assert stats["total_items"] == 42
        assert stats["library_id"] == "12345"
