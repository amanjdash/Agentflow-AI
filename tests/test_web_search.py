"""Tests for the DuckDuckGo web search tool."""

from unittest.mock import MagicMock, patch
import pytest
from app.tools.web_search import sanitize_search_query, web_search


class TestWebSearchTool:
    """Verifies search sanitization, error resilience, retry, and formatting."""

    def test_query_sanitization(self):
        dirty = "Nvidia stock \x00\x08price & quarterly \n\t earnings"
        clean = sanitize_search_query(dirty, max_length=50)
        assert "\x00" not in clean
        assert "\x08" not in clean
        assert clean == "Nvidia stock price & quarterly earnings"

    def test_oversized_query_truncated(self):
        long_query = "semiconductor " * 50
        clean = sanitize_search_query(long_query, max_length=100)
        assert len(clean) <= 100

    @patch("app.tools.web_search._perform_ddg_query")
    def test_successful_search_result(self, mock_ddg):
        mock_ddg.return_value = [
            {
                "title": "NVIDIA Corporation (NVDA) Stock Price",
                "url": "https://finance.yahoo.com/quote/NVDA",
                "snippet": "Get NVIDIA Corp stock quote, news, and financials.",
            }
        ]
        res = web_search("Nvidia stock price", max_results=1)
        assert res["success"] is True
        assert res["count"] == 1
        assert len(res["results"]) == 1
        assert res["results"][0]["title"] == "NVIDIA Corporation (NVDA) Stock Price"

    @patch("app.tools.web_search._perform_ddg_query")
    def test_empty_search_result(self, mock_ddg):
        mock_ddg.return_value = []
        res = web_search("query_with_no_possible_matches_xyz_12345")
        assert res["success"] is True
        assert res["count"] == 0
        assert res["results"] == []

    @patch("app.tools.web_search._perform_ddg_query")
    def test_search_timeout_and_fallback(self, mock_ddg):
        # Simulate timeout exception
        mock_ddg.side_effect = TimeoutError("Connection timed out to search service")
        res = web_search("ai industry growth")
        assert res["success"] is False
        assert "unavailable" in res["error"].lower()
        assert res["results"] == []

    @patch("app.tools.web_search._perform_ddg_query")
    def test_search_retry_on_transient_failure(self, mock_ddg):
        # First call fails with rate limit 429, second call succeeds
        mock_ddg.side_effect = [
            Exception("HTTP 429 Rate Limit Exceeded"),
            [{"title": "Recovered", "url": "https://example.com", "snippet": "Success"}]
        ]
        res = web_search("semiconductors", timeout_seconds=1.0)
        assert res["success"] is True
        assert res["count"] == 1
        assert res["results"][0]["title"] == "Recovered"

    def test_empty_query_rejected(self):
        res = web_search("   ")
        assert res["success"] is False
        assert "empty" in res["error"].lower()
