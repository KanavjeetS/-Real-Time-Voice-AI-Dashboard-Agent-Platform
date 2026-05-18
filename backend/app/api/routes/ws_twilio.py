"""
AI Calling Agent — Twilio Media Stream WebSocket Handler
"""
import asyncio
import base64
import json
import time
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.stt import STTService
from app.services.tts import TTSService
from app.services.crm import CRMService
from app.services.defaults import DEFAULT_AGENT_ID, DEFAULT_SYSTEM_PROMPT
from app.conversation.orchestrator import ConversationOrchestrator
from app.conversation.memory import MemoryStore
from app.observability.latency import TurnLatency, LatencyAggregator
from app.observability.tracing import bind_call_context, clear_call_context
from app.workers.queue import enqueue, JobType
from app.utils.language import resolve_conversation_language

log = structlog.get_logger()
router = APIRouter()

_inference_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_CALLS)

VAD_SILENCE_THRESHOLD_MS = settings.VAD_SILENCE_THRESHOLD_MS
VAD_MIN_UTTERANCE_BYTES = settings.VAD_MIN_UTTERANCE_BYTES
VAD_ENERGY_THRESHOLD = 200
CALL_TIMEOUT_SECONDS = settings.CALL_TIMEOUT_SECONDS
MULAW_CHUNK_BYTES = 160  # 20 ms @ 8 kHz G.711


class CallSession:
    """Per-call state container."""

    def __init__(self, call_sid: str, agent_id: Optional[str] = None):
        self.call_sid = call_sid
        self.agent_id = agent_id or DEFAULT_AGENT_ID
        self.call_db_id: Optional[uuid.UUID] = None
        self.phone_number: str = ""
        self.turn_index: int = 0
        self.conversation_history: list[dict] = []
        self.detected_language: str = "en"
        self.current_intent: str = "neutral"
        self.audio_buffer: bytearray = bytearray()
        self.is_speaking: bool = False
        self.last_speech_time: float = time.monotonic()
        self.call_start_time: float = time.monotonic()
        self.tts_playing: bool = False
        self._slack_sent: bool = False
        self.lead_score: float = 0.0
        self.intent_confidence: float = 0.0
        self.dialogue_state: str = "greeting"
        self.was_interrupted: bool = False
        self.system_prompt: str = DEFAULT_SYSTEM_PROMPT
        self._processing_turn: bool = False


@router.websocket("/ws/twilio")
async def twilio_media_stream(websocket: WebSocket):
    """Twilio Media Streams WebSocket endpoint."""
    await websocket.accept()
    state: dict = {"session": None}

    try:
        await asyncio.wait_for(
            _handle_call(websocket, state),
            timeout=CALL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        sid = state["session"].call_sid if state["session"] else "unknown"
        log.warning("call.timeout", call_sid=sid)
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        sid = state["session"].call_sid if state["session"] else "unknown"
        log.info("call.disconnected", call_sid=sid)
    except Exception as e:
        log.error("call.error", error=str(e), exc_info=True)
    finally:
        if state["session"]:
            await _finalize_call(state["session"])
        clear_call_context()


async def _handle_call(websocket: WebSocket, state: dict):
    """Main call handling loop."""
    session: Optional[CallSession] = None
    stream_sid: Optional[str] = None

    async for raw_msg in websocket.iter_text():
        try:
            msg = json.loads(raw_msg)
        except json.JSONDecodeError:
            continue

        event = msg.get("event")

        if event == "connected":
            log.info("twilio.connected")

        elif event == "start":
            start_data = msg.get("start", {})
            call_sid = start_data.get("callSid", f"local-{uuid.uuid4().hex[:8]}")
            stream_sid = start_data.get("streamSid") or msg.get("streamSid")
            custom_params = _parse_custom_parameters(start_data.get("customParameters"))
            agent_id = custom_params.get("agentId") or DEFAULT_AGENT_ID

            session = CallSession(call_sid=call_sid, agent_id=agent_id)
            session.phone_number = (
                custom_params.get("to")
                or start_data.get("to", "")
                or start_data.get("from", "")
            )
            state["session"] = session
            bind_call_context(call_sid)

            log.info("call.started", call_sid=call_sid, phone=session.phone_number, agent_id=agent_id)
            try:
                await CRMService.create_call_record(session)
            except Exception as e:
                log.warning("call.create_record_skipped", error=str(e))

            agent = await CRMService.get_agent(agent_id)
            if agent:
                session.system_prompt = agent.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
            greeting = (
                f"Hi, this is {agent['name'].split()[0] if agent else 'Priya'} from the loans team. How are you?"
                if agent
                else "Hi, this is Priya from the loans team. How are you?"
            )
            try:
                await _generate_and_send_tts(websocket, session, stream_sid, greeting, language="en")
            except Exception as e:
                log.error("call.greeting_tts_failed", error=str(e), exc_info=True)

        elif event == "media" and session and stream_sid:
            payload = msg.get("media", {}).get("payload", "")
            if not payload:
                continue

            mulaw_audio = base64.b64decode(payload)
            pcm_audio = mulaw_to_pcm16(mulaw_audio)
            energy = compute_rms(pcm_audio)

            if energy > VAD_ENERGY_THRESHOLD:
                session.audio_buffer.extend(pcm_audio)
                session.is_speaking = True
                session.last_speech_time = time.monotonic()
                if session.tts_playing:
                    await send_clear(websocket, stream_sid)
                    session.tts_playing = False
                    session.was_interrupted = True

            elif session.is_speaking:
                silence_ms = (time.monotonic() - session.last_speech_time) * 1000
                if (
                    silence_ms >= VAD_SILENCE_THRESHOLD_MS
                    and len(session.audio_buffer) >= VAD_MIN_UTTERANCE_BYTES
                    and not session._processing_turn
                ):
                    utterance_audio = bytes(session.audio_buffer)
                    session.audio_buffer = bytearray()
                    session.is_speaking = False
                    session._processing_turn = True
                    asyncio.create_task(
                        _process_utterance(websocket, session, stream_sid, utterance_audio)
                    )

        elif event == "stop" and session:
            log.info("call.stop_received", call_sid=session.call_sid)
            break


async def _process_utterance(
    websocket: WebSocket,
    session: CallSession,
    stream_sid: str,
    audio_bytes: bytes,
):
    """Layer 1+2: STT → Conversation Engine → streaming TTS."""
    try:
        async with _inference_semaphore:
            latency = TurnLatency(call_sid=session.call_sid, turn_index=session.turn_index)

            stt_result = await STTService.transcribe(
                audio_bytes,
                hint_language=session.detected_language,
            )
            latency.mark_stt(stt_result["latency_ms"])
            transcript = stt_result["transcript"]

            if not transcript.strip():
                return

            language = resolve_conversation_language(
                transcript,
                stt_result.get("language"),
                session.detected_language,
            )
            session.detected_language = language
            if session.was_interrupted:
                transcript = f"[Customer interrupted] {transcript}"
                session.was_interrupted = False

            log.info(
                "turn.user_speech",
                call_sid=session.call_sid,
                transcript=transcript[:100],
                language=language,
                latency_ms=stt_result["latency_ms"],
            )

            session.conversation_history.append({"role": "user", "content": transcript})

            orch = await ConversationOrchestrator.process_turn(
                call_sid=session.call_sid,
                turn_index=session.turn_index,
                user_text=transcript,
                language=language,
                conversation_history=session.conversation_history,
                system_prompt=session.system_prompt,
                latency=latency,
            )

            response_text = orch.response
            session.current_intent = orch.intent
            session.intent_confidence = orch.intent_confidence
            session.dialogue_state = orch.dialogue_state
            session.lead_score = orch.lead_score
            session.conversation_history.append({"role": "assistant", "content": response_text})

            log.info(
                "turn.agent_response",
                call_sid=session.call_sid,
                response=response_text[:100],
                intent=orch.intent,
                confidence=orch.intent_confidence,
                state=orch.dialogue_state,
                lead_score=orch.lead_score,
            )

            tts_start = time.monotonic()
            await _generate_and_send_tts(
                websocket, session, stream_sid, response_text, language=language
            )
            latency.mark_tts(int((time.monotonic() - tts_start) * 1000))

            breakdown = latency.finish()
            LatencyAggregator.record(breakdown)
            turn_idx = session.turn_index
            session.turn_index += 1
            asyncio.create_task(
                CRMService.save_turn(
                    session,
                    transcript,
                    response_text,
                    language,
                    breakdown["total_ms"],
                    turn_index=turn_idx,
                )
            )

            if orch.notify_slack and not session._slack_sent:
                session._slack_sent = True
                await enqueue(
                    JobType.SLACK_ALERT,
                    {
                        "call_sid": session.call_sid,
                        "phone": session.phone_number,
                        "transcript": transcript,
                        "intent": orch.intent,
                        "language": language,
                    },
                )

            if orch.should_end_call:
                await asyncio.sleep(2)
                await websocket.close(code=1000)

    except Exception as e:
        log.error("turn.process_error", call_sid=session.call_sid, error=str(e), exc_info=True)
    finally:
        session._processing_turn = False


async def _generate_and_send_tts(
    websocket: WebSocket,
    session: CallSession,
    stream_sid: Optional[str],
    text: str,
    language: str = "en",
) -> None:
    """Synthesize TTS and stream mulaw chunks to Twilio."""
    if not stream_sid:
        return
    audio_bytes = await TTSService.synthesize(text, language=language)
    if not audio_bytes:
        return

    session.tts_playing = True
    for i in range(0, len(audio_bytes), MULAW_CHUNK_BYTES):
        chunk = audio_bytes[i : i + MULAW_CHUNK_BYTES]
        await websocket.send_json({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": base64.b64encode(chunk).decode("utf-8")},
        })

    mulaw_duration_s = len(audio_bytes) / 8000.0
    asyncio.create_task(_reset_tts_flag(session, mulaw_duration_s))


async def _reset_tts_flag(session: CallSession, delay: float):
    await asyncio.sleep(max(delay, 0.1))
    session.tts_playing = False


async def send_clear(websocket: WebSocket, stream_sid: str):
    await websocket.send_json({"event": "clear", "streamSid": stream_sid})


async def _finalize_call(session: CallSession):
    await CRMService.finalize_call(session)
    await MemoryStore.delete(session.call_sid)
    if session.call_db_id:
        await enqueue(
            JobType.POST_CALL_SUMMARY,
            {
                "call_db_id": str(session.call_db_id),
                "call_sid": session.call_sid,
                "language": session.detected_language,
            },
        )
        await enqueue(
            JobType.LEAD_SCORE_SYNC,
            {
                "call_db_id": str(session.call_db_id),
                "lead_score": session.lead_score,
                "intent": session.current_intent,
            },
        )


def _parse_custom_parameters(raw) -> dict:
    """Twilio may send customParameters as dict or list of {name, value}."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        out = {}
        for item in raw:
            if isinstance(item, dict) and "name" in item and "value" in item:
                out[str(item["name"])] = str(item["value"])
        return out
    return {}


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    try:
        import audioop
        return audioop.ulaw2lin(mulaw_bytes, 2)
    except ImportError:
        result = []
        for byte in mulaw_bytes:
            byte = ~byte & 0xFF
            sign = byte & 0x80
            exponent = (byte >> 4) & 0x07
            mantissa = byte & 0x0F
            sample = ((mantissa << 1) + 33) << (exponent + 2)
            if sign:
                sample = -sample
            result.append(max(-32768, min(32767, sample)))
        import struct
        return struct.pack(f"<{len(result)}h", *result)


def compute_rms(pcm_bytes: bytes) -> float:
    import struct
    if len(pcm_bytes) < 2:
        return 0.0
    samples = struct.unpack(f"<{len(pcm_bytes) // 2}h", pcm_bytes[: len(pcm_bytes) // 2 * 2])
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5
