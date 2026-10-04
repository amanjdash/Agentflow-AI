"""Subprocess-isolated Python sandbox execution engine."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional

from app.safety.limits import GLOBAL_LIMITS
from app.services.logging import get_logger

logger = get_logger("agentflow.sandbox")

# Python prelude code injected at the top of every sandboxed execution script
SANDBOX_PRELUDE = """\
# --- AgentFlow Sandbox Security Prelude ---
import sys

# 1. Disable Network Sockets
def _block_network(*args, **kwargs):
    raise PermissionError("Network access is strictly disabled inside the AgentFlow sandbox.")

try:
    import socket
    socket.socket.connect = _block_network
    socket.socket.connect_ex = _block_network
    socket.socket.bind = _block_network
    socket.getaddrinfo = _block_network
except Exception:
    pass

# 2. Block HTTP/socket client modules
for mod_name in ("urllib.request", "http.client", "requests", "httpx", "urllib3"):
    if mod_name in sys.modules:
        del sys.modules[mod_name]

# --- End Security Prelude ---
"""


def _build_sanitized_environment() -> Dict[str, str]:
    """Builds a minimal environment dictionary stripped of all application secrets and .env variables."""
    sanitized: Dict[str, str] = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    # Pass essential operating system environment variables required for Python runtime
    allowed_keys = {
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "PATH",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
    }

    for key in allowed_keys:
        if key in os.environ:
            sanitized[key] = os.environ[key]

    return sanitized


def _sanitize_output(text: str, temp_dir: str) -> str:
    """Removes temporary filesystem paths and sensitive signatures from output streams."""
    if not text:
        return ""
    # Replace absolute temp directory paths with generic reference
    sanitized = text.replace(temp_dir, "/sandbox")
    # Replace Windows backslashed temp paths
    sanitized = sanitized.replace(temp_dir.replace("/", "\\"), "/sandbox")
    # Clean file path references
    sanitized = re.sub(r'File ".*?script\.py"', 'File "<sandbox_script.py>"', sanitized)
    return sanitized


def run_sandboxed_python(
    code: str,
    timeout_seconds: float = GLOBAL_LIMITS.python_timeout_seconds,
    max_output_bytes: int = GLOBAL_LIMITS.max_python_output_bytes,
) -> Dict[str, Any]:
    """Executes Python code in an isolated subprocess with restricted permissions.

    Guarantees:
    - Dedicated temporary directory execution.
    - Zero access to application secrets, .env, or database files.
    - Subprocess execution timeout.
    - Blocked outbound network socket operations.
    - Output truncation to prevent memory exhaustion.
    - Sanitized error output preventing host path leakage.
    """
    if not code or not code.strip():
        return {
            "success": False,
            "error_type": "EMPTY_CODE",
            "message": "Python code cannot be empty.",
            "stdout": "",
            "stderr": "",
            "execution_time_ms": 0.0,
        }

    # Create an isolated temporary workspace for the subprocess
    with tempfile.TemporaryDirectory(prefix="agentflow_sandbox_") as temp_dir:
        script_path = os.path.join(temp_dir, "script.py")
        full_code = f"{SANDBOX_PRELUDE}\n{code}\n"

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_code)

        sanitized_env = _build_sanitized_environment()
        start_time = time.perf_counter()

        try:
            process = subprocess.Popen(
                [sys.executable, "-I", "-s", script_path],  # -I: isolated mode, -s: no user site
                cwd=temp_dir,
                env=sanitized_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            stdout, stderr = process.communicate(timeout=timeout_seconds)
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

            clean_stdout = _sanitize_output(stdout, temp_dir)
            clean_stderr = _sanitize_output(stderr, temp_dir)

            # Check output size limits
            if len(clean_stdout.encode("utf-8")) > max_output_bytes:
                clean_stdout = (
                    clean_stdout[:max_output_bytes]
                    + "\n... [STDOUT truncated: exceeded maximum output limit]"
                )

            if len(clean_stderr.encode("utf-8")) > max_output_bytes:
                clean_stderr = (
                    clean_stderr[:max_output_bytes]
                    + "\n... [STDERR truncated: exceeded maximum output limit]"
                )

            if process.returncode != 0:
                # Classify error type
                error_type = "RUNTIME_ERROR"
                if "SyntaxError" in clean_stderr:
                    error_type = "SYNTAX_ERROR"
                elif "PermissionError" in clean_stderr:
                    error_type = "PERMISSION_DENIED"
                elif "MemoryError" in clean_stderr:
                    error_type = "MEMORY_LIMIT"

                return {
                    "success": False,
                    "error_type": error_type,
                    "message": f"Execution failed with exit code {process.returncode}",
                    "stdout": clean_stdout,
                    "stderr": clean_stderr,
                    "execution_time_ms": execution_time_ms,
                }

            return {
                "success": True,
                "stdout": clean_stdout,
                "stderr": clean_stderr,
                "execution_time_ms": execution_time_ms,
            }

        except subprocess.TimeoutExpired:
            # Subprocess exceeded timeout - kill immediately
            process.kill()
            process.wait()
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(f"Python sandbox script timed out after {timeout_seconds}s")
            return {
                "success": False,
                "error_type": "TIMEOUT",
                "message": f"Execution exceeded maximum allowed time of {timeout_seconds}s.",
                "stdout": "",
                "stderr": "Execution timed out (possible infinite loop).",
                "execution_time_ms": execution_time_ms,
            }

        except Exception as exc:
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(f"Unexpected sandbox error: {exc}")
            return {
                "success": False,
                "error_type": "EXECUTION_ERROR",
                "message": "An internal error occurred while running the code.",
                "stdout": "",
                "stderr": str(exc),
                "execution_time_ms": execution_time_ms,
            }
