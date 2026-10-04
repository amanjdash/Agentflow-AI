"""AgentFlow configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load .env if present
load_dotenv()


@dataclass
class AgentConfig:
    """Central configuration for the AgentFlow ReAct agent and runtime bounds."""

    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))

    database_path: str = os.getenv("DATABASE_PATH", "data/agentflow.db")

    max_agent_iterations: int = int(os.getenv("MAX_AGENT_ITERATIONS", "8"))
    max_tool_calls: int = int(os.getenv("MAX_TOOL_CALLS", "12"))
    max_request_time_seconds: float = float(os.getenv("MAX_REQUEST_TIME_SECONDS", "60.0"))
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))

    # Cost calculation settings
    input_cost_per_million: float = float(os.getenv("INPUT_COST_PER_MILLION", "0.15"))
    output_cost_per_million: float = float(os.getenv("OUTPUT_COST_PER_MILLION", "0.60"))


def get_agent_config() -> AgentConfig:
    """Builds and returns the agent configuration."""
    return AgentConfig()
