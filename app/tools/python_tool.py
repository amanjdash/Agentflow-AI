"""Python execution tool providing safe calculations via sandboxed subprocess execution."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.safety.sandbox import run_sandboxed_python
from app.services.logging import get_logger

logger = get_logger("agentflow.tools.python_tool")


def execute_python(code: str) -> Dict[str, Any]:
    """Executes Python code in a secure, isolated sandbox for mathematical and statistical calculations.

    Args:
        code: A valid Python script string to execute. Example:
              `sales = [120, 150, 180]; print(sum(sales) / len(sales))`

    Returns:
        Structured result dictionary:
        {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "execution_time_ms": float,
            "error_type": Optional[str],
            "message": Optional[str]
        }
    """
    if not isinstance(code, str) or not code.strip():
        return {
            "success": False,
            "error_type": "INVALID_ARGUMENT",
            "message": "Python code must be a non-empty string.",
            "stdout": "",
            "stderr": "",
            "execution_time_ms": 0.0,
        }

    try:
        result = run_sandboxed_python(code)
        if result["success"]:
            logger.info(f"Sandboxed Python completed successfully in {result['execution_time_ms']}ms")
        else:
            logger.warning(
                f"Sandboxed Python failed ({result.get('error_type')}): {result.get('message')}"
            )
        return result
    except Exception as exc:
        logger.error(f"Execution error in Python tool: {exc}")
        return {
            "success": False,
            "error_type": "UNEXPECTED_ERROR",
            "message": f"Execution failed: {str(exc)}",
            "stdout": "",
            "stderr": "",
            "execution_time_ms": 0.0,
        }
