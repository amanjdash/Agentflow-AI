"""Token budgeting, cost estimation, and tool result compression services."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.logging import get_logger

logger = get_logger("agentflow.token_budget")

# Default pricing in USD per 1,000,000 tokens (Gemini 2.5 Flash reference)
DEFAULT_INPUT_COST_PER_MILLION = 0.15
DEFAULT_OUTPUT_COST_PER_MILLION = 0.60


@dataclass
class TokenUsageMetrics:
    """Tracks token consumption, call counts, and estimated cost across an agent request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    estimated_cost_usd: float = 0.0

    def record_llm_call(self, prompt_toks: int, completion_toks: int) -> None:
        """Accumulates token usage and updates cost estimates."""
        self.llm_calls += 1
        self.prompt_tokens += max(0, prompt_toks)
        self.completion_tokens += max(0, completion_toks)
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.recompute_cost()

    def record_tool_call(self) -> None:
        """Increments tool invocation count."""
        self.tool_calls += 1

    def recompute_cost(
        self,
        input_cost_per_m: float = DEFAULT_INPUT_COST_PER_MILLION,
        output_cost_per_m: float = DEFAULT_OUTPUT_COST_PER_MILLION,
    ) -> float:
        """Recomputes estimated cost based on per-million token pricing."""
        input_cost = (self.prompt_tokens / 1_000_000) * input_cost_per_m
        output_cost = (self.completion_tokens / 1_000_000) * output_cost_per_m
        self.estimated_cost_usd = round(input_cost + output_cost, 6)
        return self.estimated_cost_usd

    def to_dict(self) -> Dict[str, Any]:
        """Converts usage metrics to serializable dictionary."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


def compress_tool_result(result: Any, max_chars: int = 2000) -> str:
    """Compresses or truncates bulky tool outputs before feeding them back into the LLM context.

    Prevents context bloat and token exhaustion while preserving semantic structure.
    """
    if result is None:
        return ""

    if isinstance(result, (dict, list)):
        raw_str = json.dumps(result, ensure_ascii=False)
    else:
        raw_str = str(result)

    if len(raw_str) <= max_chars:
        return raw_str

    # If the output is a JSON array or object, attempt structured compression
    if isinstance(result, list) and len(result) > 5:
        sample = result[:5]
        summary = (
            f"[Truncated: showing first 5 of {len(result)} items to conserve token budget]\n"
            f"{json.dumps(sample, ensure_ascii=False)}\n"
            f"... ({len(result) - 5} additional items truncated)"
        )
        if len(summary) <= max_chars:
            return summary

    # General character truncation with explicit boundary notice
    truncated = raw_str[:max_chars]
    return f"{truncated}\n... [Result truncated to {max_chars} characters to protect token budget]"


def estimate_string_tokens(text: str) -> int:
    """Provides a fast, approximate token count (approx 4 characters per token for English)."""
    if not text:
        return 0
    return max(1, len(text) // 4)
