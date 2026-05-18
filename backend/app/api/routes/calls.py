"""AI Calling Agent — Calls API Routes"""
import structlog
from fastapi import APIRouter, HTTPException, Query, Form
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.core.config import settings
from app.services.crm import CRMService
from app.utils.phone import normalize_phone_e164, format_twilio_error

log = structlog.get_logger()
router = APIRouter()


class InitiateCallRequest(BaseModel):
    phone_number: str = Field(..., description="E.164 or 10-digit mobile (default region from config)")
    agent_id: Optional[str] = Field(None, description="Agent UUID to use for this call")
    lead_name: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone_e164(v, default_region=settings.DEFAULT_PHONE_REGION)
        except ValueError as e:
            raise ValueError(str(e)) from e


@router.post("/calls/initiate")
async def initiate_call(req: InitiateCallRequest):
    """
    Trigger an outbound Twilio call to a phone number.
    The AI agent will handle the conversation via the WebSocket endpoint.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Twilio credentials not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env",
        )

    to_number = req.phone_number  # already normalized by validator

    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        agent_qs = f"?agentId={req.agent_id}" if req.agent_id else ""
        webhook_url = f"{settings.TWILIO_WEBHOOK_BASE_URL}/api/v1/ws/twilio/twiml{agent_qs}"

        call = client.calls.create(
            to=to_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=webhook_url,
            method="POST",
            status_callback=f"{settings.TWILIO_WEBHOOK_BASE_URL}/api/v1/calls/status",
            status_callback_method="POST",
        )

        log.info("call.initiated", call_sid=call.sid, to=to_number, agent_id=req.agent_id)
        return {
            "call_sid": call.sid,
            "status": call.status,
            "to": to_number,
        }

    except TwilioRestException as e:
        log.error("call.initiate_twilio_error", code=e.code, msg=str(e))
        raise HTTPException(status_code=400, detail=format_twilio_error(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.error("call.initiate_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {format_twilio_error(e)}")


@router.post("/ws/twilio/twiml")
async def twiml_connect(agentId: str = Query(default="")):
    """
    TwiML endpoint: connect call audio to our WebSocket stream.
    Passes agentId as a Stream custom parameter for the media handler.
    """
    from fastapi.responses import Response

    ws_url = (
        settings.TWILIO_WEBHOOK_BASE_URL.replace("https://", "wss://")
        .replace("http://", "ws://")
        + "/api/v1/ws/twilio"
    )
    param_xml = (
        f'        <Parameter name="agentId" value="{agentId}" />\n'
        if agentId
        else ""
    )
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
{param_xml}        </Stream>
    </Connect>
</Response>"""
    log.info("twiml.generated", ws_url=ws_url, agent_id=agentId or "default")
    return Response(content=twiml, media_type="application/xml")


@router.post("/calls/status")
async def call_status_callback(
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
    To: str = Form(default=""),
    From: str = Form(default=""),
):
    """Twilio status callback — updates call status in DB when configured."""
    log.info("call.status_callback", call_sid=CallSid, status=CallStatus, to=To, from_=From)
    if CallSid and CallStatus and settings.db_configured:
        await CRMService.update_call_status(CallSid, CallStatus)
    return {"received": True}


@router.get("/calls")
async def list_calls(limit: int = 50, offset: int = 0):
    """List recent calls from CRM."""
    stats = await CRMService.get_dashboard_stats()
    calls = stats.get("recent_calls", [])
    return {
        "calls": calls[offset : offset + limit],
        "total": stats.get("total_calls_today", len(calls)),
    }
