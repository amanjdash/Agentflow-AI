"""Web search tool utilizing DuckDuckGo search with sanitization, retry, and truncation."""

from __future__ import annotations

import re
import time
import warnings
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from app.safety.limits import GLOBAL_LIMITS
from app.services.logging import get_logger
from app.services.retry import retry_with_exponential_backoff

logger = get_logger("agentflow.tools.web_search")

CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def sanitize_search_query(query: str, max_length: int = GLOBAL_LIMITS.max_web_search_query_length) -> str:
    """Sanitizes user query by removing control characters and capping length."""
    if not query:
        return ""
    # Remove control characters
    cleaned = CONTROL_CHARS_REGEX.sub(" ", query)
    # Collapse multiple whitespace
    cleaned = " ".join(cleaned.split())
    # Truncate to maximum allowed length
    return cleaned[:max_length].strip()


def _perform_ddg_query(query: str, max_results: int, timeout_seconds: float) -> List[Dict[str, str]]:
    """Internal caller executing DuckDuckGo search with timeout and backoff."""
    results: List[Dict[str, str]] = []
    with DDGS(timeout=timeout_seconds) as ddgs:
        raw_results = ddgs.text(query, max_results=max_results)
        if raw_results:
            for item in raw_results:
                title = item.get("title", "")
                url = item.get("href", item.get("url", ""))
                body = item.get("body", item.get("snippet", ""))

                # Truncate individual snippets to avoid token bloat
                snippet = body[:300] + ("..." if len(body) > 300 else "")

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })
    return results


@retry_with_exponential_backoff(max_retries=3, initial_delay_seconds=1.0, max_delay_seconds=5.0)
def _perform_ddg_with_retry(query: str, max_results: int, timeout_seconds: float) -> List[Dict[str, str]]:
    return _perform_ddg_query(query, max_results, timeout_seconds)


def web_search(
    query: str,
    max_results: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Executes a web search for public information using DuckDuckGo.

    Args:
        query: The search keywords or question.
        max_results: Maximum number of search results to return (default: 5).
        timeout_seconds: Network timeout in seconds (default: 10.0).

    Returns:
        Structured dictionary containing query and list of sanitized result items:
        {
            "query": "...",
            "results": [{"title": "...", "url": "...", "snippet": "... "}],
            "count": int,
            "success": bool
        }
    """
    cleaned_query = sanitize_search_query(query)
    limit = max_results or GLOBAL_LIMITS.max_web_search_results
    timeout = timeout_seconds or GLOBAL_LIMITS.web_search_timeout_seconds

    if not cleaned_query:
        return {
            "success": False,
            "query": "",
            "results": [],
            "count": 0,
            "error": "Search query cannot be empty.",
        }

    start_time = time.perf_counter()
    try:
        results = _perform_ddg_with_retry(cleaned_query, limit, timeout)
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(f"Web search completed for '{cleaned_query[:40]}' in {elapsed_ms}ms with {len(results)} results")

        return {
            "success": True,
            "query": cleaned_query,
            "results": results,
            "count": len(results),
            "execution_time_ms": elapsed_ms,
        }

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"Web search for '{cleaned_query[:40]}' encountered issue: {exc}")
        # Return graceful structured response so the agent can adapt or report external info unavailable
        return {
            "success": False,
            "query": cleaned_query,
            "results": [],
            "count": 0,
            "error": "Web search is currently unavailable or rate-limited. Please proceed without external web data.",
            "execution_time_ms": elapsed_ms,
        }
