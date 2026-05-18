"""AI Calling Agent — Agents API Routes"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.crm import CRMService

router = APIRouter()


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str
    voice_english: str = "af_sarah"
    voice_hindi: str = "af_sky"
    language_mode: str = "auto"


@router.get("/agents")
async def list_agents():
    """List all active agents."""
    agents = await CRMService.get_all_agents()
    return {"agents": agents}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get a specific agent by ID."""
    agent = await CRMService.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/agents")
async def create_agent(req: AgentCreate):
    """Create a new agent."""
    from app.core.config import settings
    if not settings.db_configured:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.call import Agent
        import uuid

        async with AsyncSessionLocal() as db:
            agent = Agent(
                name=req.name,
                description=req.description,
                system_prompt=req.system_prompt,
                voice_english=req.voice_english,
                voice_hindi=req.voice_hindi,
                language_mode=req.language_mode,
            )
            db.add(agent)
            await db.commit()
            return {"id": str(agent.id), "name": agent.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
