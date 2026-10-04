"""Read-only SQLite query execution tool with strict 7-layer defense-in-depth safety."""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database.connection import get_readonly_connection
from app.safety.limits import DB_CONCURRENCY_SEMAPHORE, GLOBAL_LIMITS
from app.safety.sql_validator import validate_sql_query
from app.services.logging import get_logger

logger = get_logger("agentflow.tools.sql_tool")

PATH_LEAK_REGEX = re.compile(r"([A-Za-z]:[\\/][^:\s]+|/(?:home|usr|var|tmp|app)[^:\s]+)")


def _sanitize_error_message(err: Exception) -> str:
    """Strips internal system paths and sensitive diagnostics from database errors."""
    raw = str(err)
    clean = PATH_LEAK_REGEX.sub("<database>", raw)
    return clean


def query_database(
    query: str,
    db_path: Optional[Path | str] = None,
    max_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """Executes a strictly validated, read-only SQL query against the business database.

    Args:
        query: The SQL query to execute. Must be a single SELECT statement.
        db_path: Optional custom database path (defaults to standard data/agentflow.db).
        max_rows: Optional row limit override (cannot exceed GLOBAL_LIMITS.max_sql_rows).

    Returns:
        Structured dictionary containing query results or error:
        {
            "success": bool,
            "rows": List[Dict[str, Any]],
            "row_count": int,
            "columns": List[str],
            "execution_time_ms": float,
            "truncated": bool,
            "error": Optional[str]
        }
    """
    row_limit = min(max_rows or GLOBAL_LIMITS.max_sql_rows, GLOBAL_LIMITS.max_sql_rows)

    # Layer 2 & 3: AST and Allowlist validation
    validation = validate_sql_query(query)
    if not validation.is_valid or not validation.sanitized_sql:
        logger.warning(f"SQL validation rejected query: {validation.error}")
        return {
            "success": False,
            "error": validation.error or "Invalid SQL query.",
            "rows": [],
            "row_count": 0,
            "columns": [],
            "execution_time_ms": 0.0,
            "truncated": False,
        }

    sanitized_query = validation.sanitized_sql
    start_time = time.perf_counter()

    # Layer 6: Concurrency bounding
    acquired = DB_CONCURRENCY_SEMAPHORE.acquire(timeout=5.0)
    if not acquired:
        return {
            "success": False,
            "error": "Database is temporarily busy. Please retry shortly.",
            "rows": [],
            "row_count": 0,
            "columns": [],
            "execution_time_ms": 0.0,
            "truncated": False,
        }

    try:
        # Layer 4: Open SQLite connection strictly in URI read-only mode (file:...db?mode=ro)
        conn = get_readonly_connection(db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(sanitized_query)
            # Fetch at most row_limit + 1 to detect if output exceeds cap
            fetched_rows = cursor.fetchmany(row_limit + 1)
            columns = [col[0] for col in cursor.description] if cursor.description else []

            # Layer 5: Enforce row limit
            truncated = len(fetched_rows) > row_limit
            final_rows = fetched_rows[:row_limit]

            rows_as_dicts: List[Dict[str, Any]] = [dict(row) for row in final_rows]
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            result: Dict[str, Any] = {
                "success": True,
                "rows": rows_as_dicts,
                "row_count": len(rows_as_dicts),
                "columns": columns,
                "execution_time_ms": elapsed_ms,
                "truncated": truncated,
            }

            if truncated:
                result["note"] = f"Output truncated to the maximum allowed limit of {row_limit} rows."

            return result

        finally:
            cursor.close()
            conn.close()

    except sqlite3.OperationalError as op_err:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        safe_msg = _sanitize_error_message(op_err)
        logger.warning(f"Database operational error: {safe_msg}")
        return {
            "success": False,
            "error": f"Database error: {safe_msg}",
            "rows": [],
            "row_count": 0,
            "columns": [],
            "execution_time_ms": elapsed_ms,
            "truncated": False,
        }

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        safe_msg = _sanitize_error_message(exc)
        logger.error(f"Unexpected database exception: {safe_msg}")
        return {
            "success": False,
            "error": f"Query execution failed: {safe_msg}",
            "rows": [],
            "row_count": 0,
            "columns": [],
            "execution_time_ms": elapsed_ms,
            "truncated": False,
        }

    finally:
        DB_CONCURRENCY_SEMAPHORE.release()
