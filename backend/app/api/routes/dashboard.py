"""AI Calling Agent — Dashboard API Routes"""
from fastapi import APIRouter
from app.services.crm import CRMService

router = APIRouter()


@router.get("/dashboard/stats")
async def dashboard_stats():
    """Return aggregated dashboard metrics."""
    return await CRMService.get_dashboard_stats()


@router.get("/crm/leads")
async def list_leads(limit: int = 50):
    """List CRM leads."""
    if not __import__('app.core.config', fromlist=['settings']).settings.db_configured:
        return {"leads": [], "warning": "Database not configured"}
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.call import Lead
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Lead).order_by(Lead.created_at.desc()).limit(limit))
            leads = result.scalars().all()
            return {
                "leads": [
                    {
                        "id": str(l.id),
                        "phone": l.phone,
                        "name": l.name,
                        "status": l.status,
                        "loan_type": l.loan_type,
                        "loan_amount": float(l.loan_amount) if l.loan_amount else None,
                    }
                    for l in leads
                ]
            }
    except Exception as e:
        return {"leads": [], "error": str(e)}
