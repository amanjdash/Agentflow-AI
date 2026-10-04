"""FastAPI route controllers for AgentFlow."""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.agent.agent import AgentFlowAgent
from app.api.schemas import ChatRequest, ChatResponse, HealthResponse
from app.database.connection import get_default_db_path, get_readonly_connection
from app.services.logging import get_logger, set_request_id

logger = get_logger("agentflow.api")

router = APIRouter()

# Global default agent instance
_default_agent: AgentFlowAgent | None = None


def get_agent() -> AgentFlowAgent:
    """Retrieves or creates the singleton AgentFlowAgent instance."""
    global _default_agent
    if _default_agent is None:
        _default_agent = AgentFlowAgent()
    return _default_agent


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """System health check endpoint verifying database connectivity."""
    db_connected = False
    try:
        db_path = get_default_db_path()
        if db_path.exists():
            conn = get_readonly_connection(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            db_connected = True
    except Exception as exc:
        logger.warning(f"Database health check failed: {exc}")
        db_connected = False

    return HealthResponse(
        status="ok",
        version="1.0.0",
        database_connected=db_connected,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    tags=["Agent"],
)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Autonomous ReAct agent task execution endpoint.

    Executes multi-step reasoning, tool invocations, and returns a sanitized final answer
    along with an observable safe execution trace.
    """
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    set_request_id(req_id)

    agent = get_agent()
    try:
        result = await agent.achat(request.message, request_id=req_id)
        return ChatResponse(
            answer=result.answer,
            tools_used=result.tools_used,
            execution_time_ms=result.execution_time_ms,
            trace=result.trace,
            token_metrics=result.token_metrics,
        )
    except ValueError as val_err:
        logger.error(f"Configuration or validation error: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error(f"Error handling chat request {req_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request with AgentFlow.",
        )


@router.post("/chat/stream", tags=["Agent"])
async def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    """Streaming endpoint delivering safe agent lifecycle events via Server-Sent Events (SSE).

    Exposes safe tool starts, completions, and the final answer without revealing internal chain-of-thought.
    """
    req_id = f"stream_{uuid.uuid4().hex[:8]}"
    agent = get_agent()

    async def sse_event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event_data in agent.astream(request.message, request_id=req_id):
                json_str = json.dumps(event_data, ensure_ascii=False)
                yield f"data: {json_str}\n\n"
        except Exception as exc:
            err_data = {"event": "error", "message": str(exc)}
            yield f"data: {json.dumps(err_data)}\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
