"""Layer 3 — Analytics & latency reporting."""
from fastapi import APIRouter
from app.observability.latency import LatencyAggregator
from app.services.crm import CRMService

router = APIRouter()


@router.get("/analytics/latency")
async def latency_breakdown():
    """Latency breakdown for judges / dashboard (STT, LLM, TTS, p95)."""
    return LatencyAggregator.summary()


@router.get("/analytics/overview")
async def analytics_overview():
    """Combined CRM stats + latency metrics."""
    stats = await CRMService.get_dashboard_stats()
    latency = LatencyAggregator.summary()
    return {
        "crm": stats,
        "latency": latency,
        "architecture_version": "4-layer-v1",
    }
