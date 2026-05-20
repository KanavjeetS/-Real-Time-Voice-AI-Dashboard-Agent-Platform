"""
Realtime streaming STT session using Deepgram WebSocket API.

This enables lower-latency turn detection than full buffered utterance STT.
"""
import asyncio
import contextlib
import json
from typing import Optional

import structlog
import websockets

from app.core.config import settings

log = structlog.get_logger()


class DeepgramStreamingSession:
    def __init__(self, call_sid: str, hint_language: Optional[str] = None):
        self.call_sid = call_sid
        self.hint_language = hint_language or "en"
        self.ws = None
        self._reader_task: Optional[asyncio.Task] = None
        self._final_transcripts: asyncio.Queue[str] = asyncio.Queue()
        self._closed = False

    async def start(self) -> bool:
        if not settings.DEEPGRAM_API_KEY:
            return False
        # endpointing lowers end-of-utterance delay while keeping accuracy reasonable.
        query = (
            "model=nova-2"
            "&encoding=linear16"
            "&sample_rate=8000"
            "&channels=1"
            "&interim_results=true"
            f"&endpointing={settings.STT_STREAM_ENDPOINTING_MS}"
            "&vad_events=true"
            "&smart_format=true"
        )
        if settings.GROQ_STT_LANGUAGE in ("en", "hi"):
            query += f"&language={settings.GROQ_STT_LANGUAGE}"
        url = f"wss://api.deepgram.com/v1/listen?{query}"
        try:
            self.ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"},
                ping_interval=15,
                ping_timeout=20,
            )
            self._reader_task = asyncio.create_task(self._reader())
            log.info("stt.stream_started", call_sid=self.call_sid)
            return True
        except Exception as e:
            log.warning("stt.stream_start_failed", call_sid=self.call_sid, error=str(e))
            return False

    async def send_audio(self, pcm_audio: bytes) -> None:
        if self._closed or not self.ws:
            return
        try:
            await self.ws.send(pcm_audio)
        except Exception as e:
            log.warning("stt.stream_send_failed", call_sid=self.call_sid, error=str(e))

    async def pop_final_transcript(self) -> Optional[str]:
        try:
            return self._final_transcripts.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def finalize(self) -> None:
        if self._closed or not self.ws:
            return
        try:
            await self.ws.send(json.dumps({"type": "Finalize"}))
        except Exception:
            pass

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.ws:
                await self.ws.close()
        except Exception:
            pass
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(Exception):
                await self._reader_task
        log.info("stt.stream_closed", call_sid=self.call_sid)

    async def _reader(self) -> None:
        try:
            async for raw in self.ws:
                try:
                    evt = json.loads(raw)
                except Exception:
                    continue
                if evt.get("type") != "Results":
                    continue
                alts = (evt.get("channel") or {}).get("alternatives") or []
                if not alts:
                    continue
                transcript = (alts[0].get("transcript") or "").strip()
                if not transcript:
                    continue
                if evt.get("is_final") or evt.get("speech_final"):
                    await self._final_transcripts.put(transcript)
                    log.debug("stt.stream_final", call_sid=self.call_sid, chars=len(transcript))
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.warning("stt.stream_reader_error", call_sid=self.call_sid, error=str(e))

