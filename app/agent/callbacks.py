"""Safe execution trace tracker and observability handlers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.logging import get_logger
from app.services.token_budget import TokenUsageMetrics

logger = get_logger("agentflow.trace")


@dataclass
class SafeTraceItem:
    """Safe, user-facing summary of an individual tool execution step.

    Explicitly excludes private chain-of-thought or internal reasoning.
    """

    step_index: int
    tool_name: str
    input_summary: str
    output_summary: str
    execution_time_ms: float
    status: str = "success"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "tool_name": self.tool_name,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "execution_time_ms": self.execution_time_ms,
            "status": self.status,
        }


class AgentTraceTracker:
    """Collects safe execution telemetry during an agent invocation."""

    def __init__(self, request_id: str = "unknown") -> None:
        self.request_id = request_id
        self.start_time: float = time.perf_counter()
        self.end_time: Optional[float] = None
        self.trace_items: List[SafeTraceItem] = []
        self.tools_used: List[str] = []
        self.token_metrics: TokenUsageMetrics = TokenUsageMetrics()
        self._current_step: int = 0

    def record_tool_call(
        self,
        tool_name: str,
        tool_args: Any,
        tool_output: Any,
        execution_time_ms: float,
        success: bool = True,
    ) -> SafeTraceItem:
        """Records a safe tool execution summary without internal reasoning."""
        self._current_step += 1
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)

        self.token_metrics.record_tool_call()

        # Sanitize input summary (truncate to 200 chars)
        input_str = str(tool_args)
        if len(input_str) > 200:
            input_summary = input_str[:197] + "..."
        else:
            input_summary = input_str

        # Sanitize output summary (truncate to 300 chars)
        out_str = str(tool_output)
        if len(out_str) > 300:
            output_summary = out_str[:297] + "..."
        else:
            output_summary = out_str

        trace_item = SafeTraceItem(
            step_index=self._current_step,
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
            execution_time_ms=round(execution_time_ms, 2),
            status="success" if success else "error",
        )
        self.trace_items.append(trace_item)
        return trace_item

    def finish(self) -> float:
        """Marks request completion and calculates total execution time in milliseconds."""
        self.end_time = time.perf_counter()
        return round((self.end_time - self.start_time) * 1000, 2)

    @property
    def total_execution_time_ms(self) -> float:
        end = self.end_time or time.perf_counter()
        return round((end - self.start_time) * 1000, 2)
