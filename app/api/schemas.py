"""Pydantic request and response schemas for the AgentFlow REST and SSE API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request payload containing natural-language user task."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language user request or analytical query.",
        examples=["Find the current price of NVIDIA stock, compare it with our company semiconductor sales, and calculate percentage difference."],
    )


class SafeTraceItemSchema(BaseModel):
    """User-facing safe trace item of a single tool execution."""

    step_index: int = Field(..., description="Step counter.")
    tool_name: str = Field(..., description="Name of the invoked tool.")
    input_summary: str = Field(..., description="Sanitized summary of arguments.")
    output_summary: str = Field(..., description="Sanitized summary of tool result.")
    execution_time_ms: float = Field(..., description="Execution duration in milliseconds.")
    status: str = Field(default="success", description="Execution outcome status.")


class ChatResponse(BaseModel):
    """Structured response from the agent containing answer, tool list, and performance metrics."""

    answer: str = Field(..., description="Synthesized final answer from the agent.")
    tools_used: List[str] = Field(
        default_factory=list,
        description="List of tools invoked during ReAct execution.",
        examples=[["web_search", "sql_query", "execute_python"]],
    )
    execution_time_ms: float = Field(
        ..., description="Total execution duration in milliseconds."
    )
    trace: Optional[List[SafeTraceItemSchema]] = Field(
        default=None,
        description="Safe tool execution trace without internal reasoning.",
    )
    token_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Token consumption and estimated cost breakdown.",
    )


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(default="ok", description="Application service status.")
    version: str = Field(default="1.0.0", description="AgentFlow API version.")
    database_connected: bool = Field(default=True, description="Database accessibility status.")
