"""Configurable execution bounds, resource caps, and concurrency guards."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SafetyLimits:
    """Configurable system limits protecting the agent from infinite loops and resource exhaustion."""

    max_agent_iterations: int = int(os.getenv("MAX_AGENT_ITERATIONS", "8"))
    max_tool_calls: int = int(os.getenv("MAX_TOOL_CALLS", "12"))
    max_request_time_seconds: float = float(os.getenv("MAX_REQUEST_TIME_SECONDS", "60.0"))

    # Tool specific caps
    max_sql_rows: int = int(os.getenv("MAX_SQL_ROWS", "100"))
    max_sql_query_length: int = int(os.getenv("MAX_SQL_QUERY_LENGTH", "2000"))
    max_sql_calls_per_request: int = int(os.getenv("MAX_SQL_CALLS", "6"))

    python_timeout_seconds: float = float(os.getenv("PYTHON_TIMEOUT_SECONDS", "5.0"))
    max_python_output_bytes: int = int(os.getenv("MAX_PYTHON_OUTPUT_BYTES", "10240"))  # 10 KB
    max_python_calls_per_request: int = int(os.getenv("MAX_PYTHON_CALLS", "4"))

    web_search_timeout_seconds: float = float(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "10.0"))
    max_web_search_calls_per_request: int = int(os.getenv("MAX_WEB_SEARCH_CALLS", "4"))
    max_web_search_query_length: int = int(os.getenv("MAX_WEB_SEARCH_QUERY_LENGTH", "200"))
    max_web_search_results: int = int(os.getenv("MAX_WEB_SEARCH_RESULTS", "5"))

    # Database concurrency limits
    max_concurrent_db_ops: int = int(os.getenv("MAX_CONCURRENT_DB_OPS", "5"))


# Default global instance
GLOBAL_LIMITS = SafetyLimits()

# Concurrency semaphore for database queries
DB_CONCURRENCY_SEMAPHORE = threading.Semaphore(GLOBAL_LIMITS.max_concurrent_db_ops)
