"""Retry and backoff mechanisms for transient external failures."""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, Optional, Sequence, Tuple, Type, TypeVar

from app.services.logging import get_logger

logger = get_logger("agentflow.retry")

T = TypeVar("T")


class NonRetryableError(Exception):
    """Base exception for errors that must never be retried."""
    pass


class SecurityViolationError(NonRetryableError):
    """Raised when security boundaries (SQL validation, sandbox access) are breached."""
    pass


class InvalidInputError(NonRetryableError):
    """Raised when tool arguments or user inputs are invalid."""
    pass


def is_transient_error(exc: BaseException) -> bool:
    """Evaluates whether an exception represents a transient failure eligible for retry."""
    if isinstance(exc, NonRetryableError):
        return False

    error_msg = str(exc).lower()
    transient_indicators = [
        "429",
        "rate limit",
        "resource exhausted",
        "quota exceeded",
        "503",
        "service unavailable",
        "502",
        "bad gateway",
        "timeout",
        "timed out",
        "connection reset",
        "connection error",
        "temporary failure",
        "duckduckgo",
    ]
    return any(indicator in error_msg for indicator in transient_indicators)


def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay_seconds: float = 10.0,
    retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Synchronous decorator for retrying transient operations with exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay_seconds
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except NonRetryableError:
                    raise
                except retryable_exceptions as exc:
                    if not is_transient_error(exc) or attempt == max_retries:
                        logger.warning(
                            f"Operation {func.__name__} failed permanently on attempt {attempt}/{max_retries}: {exc}"
                        )
                        raise
                    logger.warning(
                        f"Transient error in {func.__name__} (attempt {attempt}/{max_retries}): {exc}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay_seconds)
            raise RuntimeError(f"Exceeded max retries for {func.__name__}")

        return wrapper

    return decorator


def async_retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay_seconds: float = 10.0,
    retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Asynchronous decorator for retrying transient operations with exponential backoff."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay_seconds
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except NonRetryableError:
                    raise
                except retryable_exceptions as exc:
                    if not is_transient_error(exc) or attempt == max_retries:
                        logger.warning(
                            f"Async operation {func.__name__} failed permanently on attempt {attempt}/{max_retries}: {exc}"
                        )
                        raise
                    logger.warning(
                        f"Transient error in async {func.__name__} (attempt {attempt}/{max_retries}): {exc}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay_seconds)
            raise RuntimeError(f"Exceeded max retries for async {func.__name__}")

        return wrapper

    return decorator
