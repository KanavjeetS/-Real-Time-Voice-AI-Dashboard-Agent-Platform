"""
AI Calling Agent — CRM Service

CRITICAL FIX: Database writes are now always enabled (USE_DATABASE=true).
Handles:
- Call record creation and finalization
- Per-turn transcript storage
- Slack webhook alerts for hot intents
- Agent configuration fetching
"""
import asyncio
import uuid
import json
import time
import httpx
import structlog
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.services.defaults import DEFAULT_AGENT, DEFAULT_AGENT_ID

log = structlog.get_logger()

# In-memory agent cache (avoids DB hit on every turn)
_agent_cache: dict = {}


class CRMService:

    @classmethod
    async def get_agent(cls, agent_id: Optional[str]) -> Optional[dict]:
        """Fetch agent config by ID (with in-memory cache)."""
        if not agent_id or agent_id == DEFAULT_AGENT_ID:
            return DEFAULT_AGENT.copy()

        if agent_id in _agent_cache:
            return _agent_cache[agent_id]

        if not settings.db_configured:
            return DEFAULT_AGENT.copy()

        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Agent

            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                result = await db.execute(
                    select(Agent).where(Agent.id == uuid.UUID(agent_id))
                )
                agent = result.scalar_one_or_none()
                if agent:
                    data = {
                        "id": str(agent.id),
                        "name": agent.name,
                        "system_prompt": agent.system_prompt,
                        "voice_english": agent.voice_english,
                        "voice_hindi": agent.voice_hindi,
                    }
                    _agent_cache[agent_id] = data
                    return data
        except Exception as e:
            log.error("crm.get_agent_error", error=str(e))
        return DEFAULT_AGENT.copy()

    @classmethod
    async def get_all_agents(cls) -> list[dict]:
        """Fetch all active agents."""
        if not settings.db_configured:
            return [DEFAULT_AGENT.copy()]
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Agent
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Agent).where(Agent.is_active == True)
                )
                agents = result.scalars().all()
                if not agents:
                    return [DEFAULT_AGENT.copy()]
                return [
                    {
                        "id": str(a.id),
                        "name": a.name,
                        "description": a.description,
                        "voice_english": a.voice_english,
                        "voice_hindi": a.voice_hindi,
                        "language_mode": a.language_mode,
                    }
                    for a in agents
                ]
        except Exception as e:
            log.error("crm.get_agents_error", error=str(e))
            return [DEFAULT_AGENT.copy()]

    @classmethod
    async def create_call_record(cls, session) -> None:
        """Create initial call record in DB."""
        if not settings.db_configured:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Call

            async with AsyncSessionLocal() as db:
                agent_uuid = None
                if session.agent_id and session.agent_id != DEFAULT_AGENT_ID:
                    try:
                        agent_uuid = uuid.UUID(session.agent_id)
                    except ValueError:
                        agent_uuid = None
                call = Call(
                    call_sid=session.call_sid,
                    agent_id=agent_uuid,
                    phone_number=session.phone_number,
                    direction="outbound",
                    status="in-progress",
                    started_at=datetime.utcnow(),
                )
                db.add(call)
                await db.commit()
                session.call_db_id = call.id
                log.info("crm.call_created", call_sid=session.call_sid)
        except Exception as e:
            log.error("crm.create_call_error", error=str(e))

    @classmethod
    async def save_turn(
        cls,
        session,
        user_transcript: str,
        agent_response: str,
        language: str,
        latency_ms: int,
        turn_index: Optional[int] = None,
    ) -> None:
        """Save a conversation turn (user + agent) to DB."""
        if not settings.db_configured or not session.call_db_id:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import CallTurn

            ti = turn_index if turn_index is not None else session.turn_index
            async with AsyncSessionLocal() as db:
                # User turn
                db.add(CallTurn(
                    call_id=session.call_db_id,
                    turn_index=ti * 2,
                    speaker="user",
                    transcript=user_transcript,
                    language=language,
                    intent=session.current_intent,
                ))
                # Agent turn
                db.add(CallTurn(
                    call_id=session.call_db_id,
                    turn_index=ti * 2 + 1,
                    speaker="agent",
                    transcript=agent_response,
                    language=language,
                    intent=getattr(session, "follow_up_action", "continue"),
                    sentiment=getattr(session, "lead_score", None),
                    latency_ms=latency_ms,
                ))
                await db.commit()
        except Exception as e:
            log.error("crm.save_turn_error", error=str(e))

    @classmethod
    async def update_call_status(cls, call_sid: str, status: str) -> None:
        """Update call status from Twilio status callback."""
        if not settings.db_configured or not call_sid:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Call
            from sqlalchemy import update

            twilio_to_internal = {
                "completed": "completed",
                "busy": "no-answer",
                "no-answer": "no-answer",
                "failed": "failed",
                "canceled": "failed",
            }
            internal_status = twilio_to_internal.get(status, status)

            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Call)
                    .where(Call.call_sid == call_sid)
                    .values(status=internal_status)
                )
                await db.commit()
        except Exception as e:
            log.error("crm.update_status_error", error=str(e))

    @classmethod
    async def finalize_call(cls, session) -> None:
        """Update call record with final status and duration."""
        if not settings.db_configured or not session.call_db_id:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Call
            from sqlalchemy import update

            duration = int(time.monotonic() - session.call_start_time)
            lead_score = getattr(session, "lead_score", None)
            sentiment = float(lead_score) if lead_score is not None else None
            follow_up_action = getattr(session, "follow_up_action", "continue")

            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Call)
                    .where(Call.id == session.call_db_id)
                    .values(
                        status="completed",
                        duration_seconds=duration,
                        detected_language=session.detected_language,
                        intent_label=session.current_intent,
                        sentiment_score=sentiment,
                        summary=f"Follow-up action: {follow_up_action}",
                        ended_at=datetime.utcnow(),
                    )
                )
                await db.commit()
                await cls._update_lead_status_by_phone(
                    db=db,
                    phone=session.phone_number,
                    intent=session.current_intent,
                    follow_up_action=follow_up_action,
                )
                log.info("crm.call_finalized",
                         call_sid=session.call_sid,
                         duration_s=duration,
                         intent=session.current_intent,
                         lead_score=lead_score)
        except Exception as e:
            log.error("crm.finalize_error", error=str(e))

    @classmethod
    async def _update_lead_status_by_phone(cls, db, phone: str, intent: str, follow_up_action: str) -> None:
        """Best-effort lead status update after call finalization."""
        if not phone:
            return
        try:
            from app.models.call import Lead
            from sqlalchemy import select, update

            norm = "".join(ch for ch in phone if ch.isdigit())
            variants = {phone}
            if norm:
                variants.add(norm)
                if norm.startswith("91") and len(norm) == 12:
                    variants.add(norm[2:])

            lead = await db.scalar(select(Lead).where(Lead.phone.in_(list(variants))).limit(1))
            if not lead:
                return

            status_map = {
                "interested": "qualified",
                "high_ticket": "hot",
                "callback": "callback_scheduled",
                "confused": "follow_up_needed",
                "angry": "escalated",
                "not_interested": "closed_not_interested",
                "spam_invalid": "invalid",
            }
            new_status = status_map.get(intent, "in_progress")
            note = f"AI follow-up action: {follow_up_action}; intent: {intent}"
            await db.execute(
                update(Lead)
                .where(Lead.id == lead.id)
                .values(status=new_status, notes=note, updated_at=datetime.utcnow())
            )
            await db.commit()
        except Exception as e:
            log.warning("crm.lead_status_update_skipped", error=str(e))

    @classmethod
    async def generate_and_store_summary(
        cls,
        call_db_id: str | None,
        call_sid: str,
        language: str = "en",
    ) -> None:
        """Generate LLM call summary and persist to CRM."""
        if not settings.db_configured or not call_db_id:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Call, CallTurn
            from app.services.llm import LLMService
            from sqlalchemy import select, update
            import uuid

            async with AsyncSessionLocal() as db:
                turns = await db.execute(
                    select(CallTurn)
                    .where(CallTurn.call_id == uuid.UUID(call_db_id))
                    .order_by(CallTurn.turn_index)
                )
                lines = [
                    f"{t.speaker.upper()}: {t.transcript}"
                    for t in turns.scalars().all()
                ]
                summary = await LLMService.generate_call_summary(lines, language)
                if summary:
                    await db.execute(
                        update(Call)
                        .where(Call.id == uuid.UUID(call_db_id))
                        .values(summary=summary)
                    )
                    await db.commit()
                    log.info("crm.summary_stored", call_sid=call_sid)
        except Exception as e:
            log.error("crm.summary_error", error=str(e))

    @classmethod
    async def update_lead_score(
        cls,
        call_db_id: str | None,
        lead_score: float,
        intent: str | None,
    ) -> None:
        if not settings.db_configured or not call_db_id:
            return
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Call
            from sqlalchemy import update
            import uuid

            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Call)
                    .where(Call.id == uuid.UUID(call_db_id))
                    .values(
                        intent_label=intent,
                        sentiment_score=lead_score,
                    )
                )
                await db.commit()
        except Exception as e:
            log.error("crm.lead_score_error", error=str(e))

    @classmethod
    async def update_recording(cls, call_sid: str, recording_url: str | None, recording_status: str | None) -> None:
        """Persist Twilio recording URL for dashboard playback."""
        if not settings.db_configured or not call_sid:
            return
        if recording_url and not recording_url.endswith(".mp3"):
            recording_url = f"{recording_url}.mp3"
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Call
            from sqlalchemy import update

            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Call)
                    .where(Call.call_sid == call_sid)
                    .values(
                        recording_url=recording_url,
                    )
                )
                await db.commit()
        except Exception as e:
            log.error("crm.recording_update_error", error=str(e))

    @classmethod
    async def get_call_turns(cls, call_id: str) -> list[dict]:
        """Fetch transcript turns for a given call."""
        if not settings.db_configured:
            return []
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import CallTurn
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(CallTurn)
                    .where(CallTurn.call_id == uuid.UUID(call_id))
                    .order_by(CallTurn.turn_index.asc())
                )
                turns = result.scalars().all()
                return [
                    {
                        "turn_index": t.turn_index,
                        "speaker": t.speaker,
                        "transcript": t.transcript,
                        "language": t.language,
                        "intent": t.intent,
                        "sentiment": float(t.sentiment) if t.sentiment is not None else None,
                        "latency_ms": t.latency_ms,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                    }
                    for t in turns
                ]
        except Exception as e:
            log.error("crm.get_turns_error", error=str(e))
            return []

    @classmethod
    async def send_slack_alert(cls, session, transcript: str, intent: str) -> None:
        """Send Slack webhook for high-value intent (fires DURING call, not after)."""
        if not settings.SLACK_WEBHOOK_URL:
            return
        try:
            message = {
                "text": f"🔥 *Hot Lead Alert — {intent.upper()}*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Phone:* {session.phone_number}\n"
                                    f"*Intent:* `{intent}`\n"
                                    f"*Transcript:* _{transcript[:200]}_\n"
                                    f"*Language:* {session.detected_language}\n"
                                    f"*Call SID:* `{session.call_sid}`"
                        }
                    }
                ]
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(settings.SLACK_WEBHOOK_URL, json=message)
                log.info("slack.alert_sent", status=resp.status_code, intent=intent)
        except Exception as e:
            log.error("slack.alert_error", error=str(e))

    @classmethod
    async def get_dashboard_stats(cls) -> dict:
        """Get aggregated stats for dashboard."""
        if not settings.db_configured:
            return _mock_stats("Database disabled (USE_DATABASE=false or DATABASE_URL empty)")
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.call import Call, CallTurn
            from sqlalchemy import select, func, and_
            from datetime import timedelta

            async with AsyncSessionLocal() as db:
                # Total calls today
                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                total_today = await db.scalar(
                    select(func.count(Call.id)).where(Call.created_at >= today)
                )
                # Intent breakdown
                intents = await db.execute(
                    select(Call.intent_label, func.count(Call.id))
                    .where(Call.intent_label.isnot(None))
                    .group_by(Call.intent_label)
                )
                intent_counts = {row[0]: row[1] for row in intents}

                # Avg duration
                avg_duration = await db.scalar(
                    select(func.avg(Call.duration_seconds))
                    .where(Call.status == "completed")
                    .where(Call.created_at >= today)
                )

                # Recent calls
                recent = await db.execute(
                    select(Call).order_by(Call.created_at.desc()).limit(10)
                )
                recent_call_rows = recent.scalars().all()
                recent_calls = [
                    {
                        "id": str(c.id),
                        "call_sid": c.call_sid,
                        "phone": c.phone_number,
                        "status": c.status,
                        "intent": c.intent_label,
                        "follow_up_action": c.summary.replace("Follow-up action: ", "") if c.summary and c.summary.startswith("Follow-up action: ") else None,
                        "sentiment_score": float(c.sentiment_score) if c.sentiment_score is not None else None,
                        "recording_url": c.recording_url,
                        "duration_s": c.duration_seconds,
                        "language": c.detected_language,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                    for c in recent_call_rows
                ]

                turn_rows = await db.execute(
                    select(CallTurn.call_id, CallTurn.intent, CallTurn.speaker)
                    .where(CallTurn.speaker == "user")
                    .where(CallTurn.intent.isnot(None))
                )
                user_turns = turn_rows.all()
                total_user_intent_turns = len(user_turns)
                mismatch_turns = 0
                call_final_intent = {str(c.id): c.intent_label for c in recent_call_rows}
                for row in user_turns:
                    cid = str(row[0])
                    final_intent = call_final_intent.get(cid)
                    if final_intent and row[1] and row[1] != final_intent and row[1] != "neutral":
                        mismatch_turns += 1
                false_positive_rate = round((mismatch_turns / total_user_intent_turns) * 100, 2) if total_user_intent_turns else 0.0

                from app.observability.latency import LatencyAggregator

                return {
                    "total_calls_today": total_today or 0,
                    "avg_duration_seconds": float(avg_duration or 0),
                    "intent_breakdown": intent_counts,
                    "conversion_metrics": {
                        "qualified_calls": int((intent_counts.get("interested", 0) or 0) + (intent_counts.get("high_ticket", 0) or 0)),
                        "conversion_rate_percent": round(
                            (
                                ((intent_counts.get("interested", 0) or 0) + (intent_counts.get("high_ticket", 0) or 0))
                                / max(int(total_today or 0), 1)
                            ) * 100,
                            2,
                        ),
                    },
                    "intent_false_positive_rate_percent": false_positive_rate,
                    "recent_calls": recent_calls,
                    "active_calls": 0,
                    "latency": LatencyAggregator.summary(),
                }
        except Exception as e:
            log.error("crm.stats_error", error=str(e))
            return _mock_stats(f"Stats unavailable: {str(e)[:120]}")


def _mock_stats(warning: str = "Database not configured — showing empty stats") -> dict:
    """Fallback stats when DB is unavailable."""
    from app.observability.latency import LatencyAggregator

    return {
        "total_calls_today": 0,
        "avg_duration_seconds": 0,
        "intent_breakdown": {},
        "conversion_metrics": {
            "qualified_calls": 0,
            "conversion_rate_percent": 0.0,
        },
        "intent_false_positive_rate_percent": 0.0,
        "recent_calls": [],
        "active_calls": 0,
        "latency": LatencyAggregator.summary(),
        "_warning": warning,
    }
