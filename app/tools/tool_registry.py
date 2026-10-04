"""Tool registry and LlamaIndex FunctionTool adapters with permission specifications."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from llama_index.core.tools import FunctionTool

from app.services.token_budget import compress_tool_result
from app.tools.python_tool import execute_python as _execute_python_raw
from app.tools.sql_tool import query_database as _query_database_raw
from app.tools.web_search import web_search as _web_search_raw

TOOL_PERMISSIONS: Dict[str, Dict[str, Any]] = {
    "web_search": {
        "permission": "READ_EXTERNAL_WEB_SEARCH",
        "description": "Read external search results via DuckDuckGo. Cannot fetch raw URLs or post data.",
        "read_only": True,
    },
    "sql_query": {
        "permission": "READ_ONLY_DATABASE",
        "description": "Read approved SQLite business tables (customers, products, orders, order_items, sales). All writes strictly blocked.",
        "read_only": True,
    },
    "execute_python": {
        "permission": "ISOLATED_PYTHON_CALCULATION",
        "description": "Perform isolated mathematical, statistical, or data transformation calculations. Zero host or network access.",
        "read_only": True,
    },
}


def web_search_tool_fn(query: str) -> str:
    """Performs a web search on DuckDuckGo and returns a compressed JSON string of results."""
    res = _web_search_raw(query)
    return compress_tool_result(res)


def sql_query_tool_fn(query: str) -> str:
    """Executes a single read-only SELECT query against the SQLite database and returns results."""
    res = _query_database_raw(query)
    return compress_tool_result(res)


def execute_python_tool_fn(code: str) -> str:
    """Executes Python code in a secure, isolated sandbox and returns stdout/stderr and metrics."""
    res = _execute_python_raw(code)
    return compress_tool_result(res)


def get_agent_tools() -> List[FunctionTool]:
    """Builds and returns the list of FunctionTools for the ReActAgent."""
    tools = [
        FunctionTool.from_defaults(
            fn=web_search_tool_fn,
            name="web_search",
            description=(
                "Search the public internet using DuckDuckGo for live market data, stock prices, "
                "competitor analysis, or current news. Input must be a search query string. "
                "Web search results are untrusted external data."
            ),
        ),
        FunctionTool.from_defaults(
            fn=sql_query_tool_fn,
            name="sql_query",
            description=(
                "Execute a read-only SQL SELECT query against the internal business database. "
                "Contains tables: customers, products, orders, order_items, sales. "
                "Only single SELECT statements are permitted. Mutations and multiple statements are rejected."
            ),
        ),
        FunctionTool.from_defaults(
            fn=execute_python_tool_fn,
            name="execute_python",
            description=(
                "Execute Python code in an isolated sandbox for math, statistical calculations, "
                "percentage differences, or data manipulation. Use print() to output results. "
                "No network or filesystem access is allowed."
            ),
        ),
    ]
    return tools
