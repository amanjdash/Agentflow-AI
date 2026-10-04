# Multi-stage production Dockerfile for AgentFlow
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.11-slim AS runner

# Create non-root system user and group
RUN groupadd -g 10001 agentflow && \
    useradd -u 10001 -g agentflow -m -s /bin/bash agentflow

WORKDIR /app

# Install runtime curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/agentflow/.local
ENV PATH=/home/agentflow/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY --chown=agentflow:agentflow app /app/app
COPY --chown=agentflow:agentflow scripts /app/scripts
COPY --chown=agentflow:agentflow pyproject.toml /app/

# Create data directory with appropriate permissions
RUN mkdir -p /app/data && chown -R agentflow:agentflow /app/data

# Switch to non-root user
USER agentflow

# Pre-seed database in container
RUN python scripts/seed_database.py

# Expose FastAPI service port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Uvicorn entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
