"""Structured and observable logging system for AgentFlow.

Provides contextvars-based request ID tracking, sensitive information redaction,
and structured JSON/console log formatting.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for tracing request lifecycles across async tasks
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="system")

# Patterns for sensitive information redaction
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|auth|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?"),
    re.compile(r"(AIzaSy[A-Za-z0-9_\-]{33})"),  # Google API key format
]


def redact_sensitive_data(text: str) -> str:
    """Redacts potential secrets, API keys, and credentials from log strings."""
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1: [REDACTED]", redacted)
    return redacted


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON with contextual metadata."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": req_id,
            "message": redact_sensitive_data(record.getMessage()),
        }

        # Include structured extra fields if present
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            for k, v in record.extra_data.items():
                if isinstance(v, str):
                    payload[k] = redact_sensitive_data(v)
                else:
                    payload[k] = v

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str = "agentflow") -> logging.Logger:
    """Configures and retrieves an application logger with structured formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))
        logger.propagate = False
    return logger


def set_request_id(req_id: str) -> contextvars.Token[str]:
    """Sets the current request context ID."""
    return request_id_ctx.set(req_id)


def reset_request_id(token: contextvars.Token[str]) -> None:
    """Resets the request context ID."""
    request_id_ctx.reset(token)


class LogEvent:
    """Helper for logging structured events with standard metrics."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def tool_execution(
        self,
        tool_name: str,
        execution_time_ms: float,
        success: bool,
        input_summary: Optional[str] = None,
        error: Optional[str] = None,
        retry_count: int = 0,
    ) -> None:
        extra_data = {
            "event_type": "tool_execution",
            "tool_name": tool_name,
            "execution_time_ms": round(execution_time_ms, 2),
            "success": success,
            "retry_count": retry_count,
        }
        if input_summary:
            extra_data["input_summary"] = input_summary[:200]
        if error:
            extra_data["error"] = error

        self.logger.info(
            f"Tool {tool_name} completed in {execution_time_ms:.2f}ms (success={success})",
            extra={"extra_data": extra_data},
        )

    def agent_step(
        self,
        iteration: int,
        action: str,
        llm_calls: int = 1,
        token_usage: Optional[Dict[str, int]] = None,
    ) -> None:
        extra_data = {
            "event_type": "agent_step",
            "iteration": iteration,
            "action": action,
            "llm_calls": llm_calls,
        }
        if token_usage:
            extra_data["token_usage"] = token_usage

        self.logger.info(
            f"Agent iteration {iteration}: action={action}",
            extra={"extra_data": extra_data},
        )
