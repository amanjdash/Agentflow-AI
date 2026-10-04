"""FastAPI application entrypoint for AgentFlow."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.database.connection import get_default_db_path
from app.database.seed import seed_database
from app.services.logging import get_logger, reset_request_id, set_request_id

logger = get_logger("agentflow.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager initializing database resources on startup."""
    logger.info("AgentFlow starting up...")
    db_path = get_default_db_path()
    if not db_path.exists():
        logger.info(f"Database not found at {db_path}. Automatically seeding sample database...")
        seed_database(db_path)
    else:
        logger.info(f"Database found at {db_path}.")
    yield
    logger.info("AgentFlow shutting down...")


app = FastAPI(
    title="AgentFlow — Autonomous Multi-Tool AI Agent",
    description=(
        "Production-grade AI agent powered by ReAct reasoning, Google Gemini API, "
        "SQLite read-only querying, DuckDuckGo search, and isolated Python sandbox execution."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_and_request_id_middleware(request: Request, call_next):
    """Assigns unique request IDs and tracks HTTP request latency."""
    req_id = request.headers.get("X-Request-ID") or f"req_{int(time.time() * 1000)}"
    token = set_request_id(req_id)
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time-MS"] = f"{elapsed_ms:.2f}"
        return response
    finally:
        reset_request_id(token)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global fallback exception handler suppressing internal stack traces."""
    logger.error(f"Unhandled exception during {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "An internal server error occurred. Please check application logs."},
    )


from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


# Register API routes
app.include_router(api_router)


@app.get("/", tags=["UI"])
async def serve_ui():
    """Serves the interactive AgentFlow web chat interface."""
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return JSONResponse({
        "service": "AgentFlow — Autonomous Multi-Tool AI Agent",
        "docs": "/docs",
    })


@app.get("/api/info", tags=["System"])
async def root_info():
    """System metadata and available endpoints."""
    return {
        "service": "AgentFlow — Autonomous Multi-Tool AI Agent",
        "version": "1.0.0",
        "endpoints": {
            "ui": "/",
            "health": "/health",
            "chat": "POST /chat",
            "chat_stream": "POST /chat/stream",
            "docs": "/docs",
        },
    }
