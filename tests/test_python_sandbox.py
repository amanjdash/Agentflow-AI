"""Tests verifying Python sandbox isolation, timeouts, and resource constraints."""

import os
import pytest
from app.safety.sandbox import run_sandboxed_python
from app.tools.python_tool import execute_python


class TestPythonSandbox:
    """Verifies that the sandboxed execution environment is secure and strictly isolated."""

    def test_valid_calculation_succeeds(self):
        code = "sales = [120, 150, 180]\nprint(sum(sales) / len(sales))"
        res = execute_python(code)
        assert res["success"] is True
        assert "150.0" in res["stdout"].strip()
        assert res["execution_time_ms"] > 0

    def test_syntax_error_handled(self):
        code = "def broken(\n  return 42"
        res = execute_python(code)
        assert res["success"] is False
        assert res["error_type"] == "SYNTAX_ERROR"
        assert "SyntaxError" in res["stderr"]

    def test_runtime_error_handled(self):
        code = "result = 100 / 0"
        res = execute_python(code)
        assert res["success"] is False
        assert res["error_type"] == "RUNTIME_ERROR"
        assert "ZeroDivisionError" in res["stderr"]

    def test_infinite_loop_times_out(self):
        code = "import time\nwhile True:\n    pass"
        res = run_sandboxed_python(code, timeout_seconds=1.0)
        assert res["success"] is False
        assert res["error_type"] == "TIMEOUT"
        assert "exceeded maximum allowed time" in res["message"]

    def test_excessive_output_truncated(self):
        code = "print('X' * 20000)"
        res = run_sandboxed_python(code, max_output_bytes=500)
        assert res["success"] is True
        assert len(res["stdout"]) < 1000
        assert "truncated" in res["stdout"].lower()

    def test_environment_secrets_unavailable(self):
        # Set a sensitive key in host environment
        os.environ["GEMINI_API_KEY"] = "super_secret_test_key_12345"
        try:
            code = "import os\nprint(f'SECRET:{os.environ.get(\"GEMINI_API_KEY\")}')"
            res = execute_python(code)
            assert res["success"] is True
            assert "SECRET:None" in res["stdout"].strip()
            assert "super_secret_test_key_12345" not in res["stdout"]
        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_network_access_blocked(self):
        code = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("8.8.8.8", 53))
"""
        res = execute_python(code)
        assert res["success"] is False
        assert res["error_type"] == "PERMISSION_DENIED"
        assert "Network access is strictly disabled" in res["stderr"]

    def test_empty_code_rejected(self):
        res = execute_python("   ")
        assert res["success"] is False
        assert res["error_type"] == "INVALID_ARGUMENT"
