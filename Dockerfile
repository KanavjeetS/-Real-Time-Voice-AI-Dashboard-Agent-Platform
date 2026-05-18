# ─────────────────────────────────────────────
#  AI Calling Agent — Multi-Stage Dockerfile
#  Fixes: non-root user, multi-stage build,
#         healthcheck, vLLM separated,
#         no compiler in prod image
# ─────────────────────────────────────────────

# ── Stage 1: builder ──────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build deps (stays in this layer only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY requirements-cpu.txt ./
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements-cpu.txt

# ── Stage 2: production ───────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

# Only runtime libs — no compiler
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser backend/ .

USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# PORT is set by Railway/Render; use 1 worker for WebSocket stickiness
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
