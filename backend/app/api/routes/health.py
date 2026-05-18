"""AI Calling Agent — Health Check"""
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    db_ok = False
    db_crm_ready = False
    if settings.db_configured:
        try:
            from app.db.session import AsyncSessionLocal
            if AsyncSessionLocal:
                from sqlalchemy import text
                async with AsyncSessionLocal() as db:
                    await db.execute(text("SELECT 1"))
                db_ok = True
                try:
                    async with AsyncSessionLocal() as db:
                        await db.execute(text("SELECT 1 FROM agents LIMIT 1"))
                    db_crm_ready = True
                except Exception:
                    db_crm_ready = False
        except Exception:
            db_ok = False

    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "tier": settings.MODEL_TIER,
        "db_enabled": settings.db_configured,
        "db_connected": db_ok,
        "db_crm_ready": db_crm_ready,
        "groq_configured": bool(settings.GROQ_API_KEY),
        "twilio_configured": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN),
    }
