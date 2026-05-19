"""
AI Calling Agent — FastAPI Application Entry Point
"""
import os
# Kokoro ONNX reads UTF-8 vocab JSON; required on Windows (cp1252 breaks import).
os.environ.setdefault("PYTHONUTF8", "1")

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import init_db, close_db
from app.db.redis_client import close_redis
from app.api.routes import calls, dashboard, agents, health, debug, ws_twilio, analytics

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    log.info("vahanai.startup", env=settings.APP_ENV, tier=settings.MODEL_TIER)
    await init_db()
    if settings.STARTUP_WARM_MODELS:
        from app.services.stt import STTService
        from app.services.tts import TTSService
        await STTService.warm_up()
        await TTSService.warm_up()
        log.info("vahanai.models_warmed")
    yield
    log.info("vahanai.shutdown")
    await close_db()
    await close_redis()


app = FastAPI(
    title="AI Calling Agent API",
    version="1.0.0",
    description="AI Voice Calling Agent — Loan Follow-Up & Customer Support",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
)

# ── CORS ──────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ────────────────────────
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ── Routers ───────────────────────────────────
app.include_router(health.router, tags=["Health"])
app.include_router(calls.router, prefix="/api/v1", tags=["Calls"])
app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
app.include_router(agents.router, prefix="/api/v1", tags=["Agents"])
app.include_router(ws_twilio.router, prefix="/api/v1", tags=["Twilio WebSocket"])

# Debug endpoints — only in non-production
if settings.APP_ENV != "production":
    app.include_router(debug.router, prefix="/api/v1/debug", tags=["Debug"])
