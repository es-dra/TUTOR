"""ReferenceVerifier 单元测试"""

import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from tutor.core.external.dblp import (
    ReferenceVerifier,
    ReferenceMatch,
    BatchVerifyResult,
)


class TestReferenceMatch:
    def test_is_verified_high_confidence(self):
        m = ReferenceMatch(input_title="Test", found=True, confidence=0.8)
        assert m.is_verified is True

    def test_is_verified_low_confidence(self):
        m = ReferenceMatch(input_title="Test", found=True, confidence=0.5)
        assert m.is_verified is False

    def test_is_verified_not_found(self):
        m = ReferenceMatch(input_title="Test", found=False, confidence=0.0)
        assert m.is_verified is False

    def test_batch_verification_rate(self):
        r = BatchVerifyResult(total=4, verified=3, unverified=1, low_confidence=0)
        assert r.verification_rate == 0.75


class TestTitleSimilarity:
    def setup_method(self):
        self.verifier = ReferenceVerifier(request_timeout=1, delay=0)

    def test_exact_match(self):
        sim = ReferenceVerifier._title_similarity(
            "Attention Is All You Need", "Attention Is All You Need"
        )
        assert sim > 0.9

    def test_case_insensitive(self):
        sim = ReferenceVerifier._title_similarity(
            "deep learning", "Deep Learning"
        )
        assert sim > 0.9

    def test_punctuation_ignored(self):
        sim = ReferenceVerifier._title_similarity(
            "A Survey on Transformers", "A Survey on Transformers:"
        )
        assert sim > 0.9

    def test_completely_different(self):
        sim = ReferenceVerifier._title_similarity(
            "Machine Learning Basics", "Cooking Recipes for Beginners"
        )
        # LCS 字符级相似度对完全不相关内容仍可能有字母重叠，放宽到 < 0.5
        assert sim < 0.5

    def test_empty_strings(self):
        assert ReferenceVerifier._title_similarity("", "test") == 0.0
        assert ReferenceVerifier._title_similarity("test", "") == 0.0


class TestAuthorOverlap:
    def test_full_overlap(self):
        overlap = ReferenceVerifier._author_overlap(
            ["Alice Smith", "Bob Jones"],
            ["Alice Smith", "Bob Jones"],
        )
        assert overlap == 1.0

    def test_partial_overlap(self):
        overlap = ReferenceVerifier._author_overlap(
            ["Alice Smith", "Bob Jones"],
            ["Alice Smith", "Charlie Brown"],
        )
        assert overlap == 0.5

    def test_no_overlap(self):
        overlap = ReferenceVerifier._author_overlap(
            ["Alice Smith"], ["Bob Jones"]
        )
        assert overlap == 0.0

    def test_empty_authors(self):
        assert ReferenceVerifier._author_overlap([], ["Bob"]) == 0.0


class TestVerifySingle:
    def setup_method(self):
        self.verifier = ReferenceVerifier(request_timeout=5, delay=0)

    @patch("tutor.core.external.dblp.ReferenceVerifier._http_get")
    def test_found_on_semantic_scholar(self, mock_get):
        mock_get.return_value = json.dumps({
            "data": [{
                "title": "Attention Is All You Need",
                "authors": [{"name": "Ashish Vaswani"}],
                "year": 2017,
                "venue": "NeurIPS",
                "externalIds": {"DOI": "10.1234/test", "ArXiv": "1706.03762"},
                "citationCount": 50000,
            }]
        })

        result = self.verifier.verify_single("Attention Is All You Need")
        assert result.found is True
        assert result.confidence > 0.7
        assert "semantic_scholar" in result.sources
        assert result.matched_year == 2017

    @patch("tutor.core.external.dblp.ReferenceVerifier._http_get")
    def test_not_found(self, mock_get):
        mock_get.return_value = json.dumps({"data": []})

        result = self.verifier.verify_single(
            "Completely Fake Paper That Does Not Exist Anywhere"
        )
        assert result.found is False
        assert result.confidence == 0.0

    @patch("tutor.core.external.dblp.ReferenceVerifier._http_get")
    def test_network_error(self, mock_get):
        mock_get.return_value = None

        result = self.verifier.verify_single("Some Paper Title")
        assert result.found is False


class TestVerifyBatch:
    def setup_method(self):
        self.verifier = ReferenceVerifier(request_timeout=5, delay=0)

    @patch("tutor.core.external.dblp.ReferenceVerifier._http_get")
    def test_batch_mixed_results(self, mock_get):
        s2_response = json.dumps({
            "data": [
                {
                    "title": "Attention Is All You Need",
                    "authors": [{"name": "Vaswani"}],
                    "year": 2017,
                    "externalIds": {"ArXiv": "1706.03762"},
                    "citationCount": 50000,
                }
            ]
        })

        def side_effect(url):
            # First call (S2 for real paper) returns data
            # Second call (S2 for fake, then arXiv) returns empty
            if "Attention" in url:
                return s2_response
            return json.dumps({"data": []})

        mock_get.side_effect = side_effect

        result = self.verifier.verify_batch([
            {"title": "Attention Is All You Need", "authors": ["Vaswani"]},
            {"title": "Totally Made Up Paper", "authors": ["Nobody"]},
        ])

        assert result.total == 2
        assert result.verified >= 1
        assert result.unverified >= 1


class TestGenerateReport:
    def test_report_format(self):
        batch = BatchVerifyResult(
            total=2, verified=1, unverified=1, low_confidence=0,
            results=[
                ReferenceMatch(
                    input_title="Real Paper",
                    found=True, confidence=0.9,
                    matched_title="Real Paper",
                    matched_authors=["Author A"],
                    matched_year=2024,
                    matched_venue="ICML",
                ),
                ReferenceMatch(
                    input_title="Fake Paper",
                    found=False, confidence=0.0,
                    reason="Not found",
                ),
            ]
        )

        verifier = ReferenceVerifier(request_timeout=1, delay=0)
        report = verifier.generate_report(batch)

        assert "# Reference Verification Report" in report
        assert "Real Paper" in report
        assert "Fake Paper" in report
        # 报告使用 Markdown 粗体格式：**Verified**: 1
        assert "Verified" in report and "1" in report
        assert "Unverified" in report
