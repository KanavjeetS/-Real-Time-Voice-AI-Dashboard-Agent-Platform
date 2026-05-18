"""
AI Calling Agent — Speech-to-Text Service

CRITICAL FIX: Language auto-detection enabled.
Audit identified GROQ_STT_LANGUAGE=hi hardcoded, breaking English callers.
This service uses Whisper multilingual mode with per-utterance language detection.
"""
import asyncio
import time
import io
import structlog
from typing import Optional
from app.core.config import settings
from app.utils.audio import pcm16_to_wav

log = structlog.get_logger()

# Twilio μ-law decode → PCM at 8 kHz mono
STT_SAMPLE_RATE = 8000

_faster_whisper_model = None
_executor = None


def _get_executor():
    global _executor
    if _executor is None:
        from concurrent.futures import ThreadPoolExecutor
        _executor = ThreadPoolExecutor(
            max_workers=max(2, (settings.MAX_CONCURRENT_CALLS // 2)),
            thread_name_prefix="stt_worker",
        )
    return _executor


class STTService:
    """
    Speech-to-Text service with automatic language detection.

    Strategy:
    - free/balanced tier: Groq Whisper API (auto-detect when language omitted)
    - full tier: local faster-whisper
    """

    @classmethod
    async def warm_up(cls):
        """Pre-load models on startup to avoid cold-start latency."""
        if settings.MODEL_TIER in ("balanced", "full"):
            log.info("stt.warming_up", tier=settings.MODEL_TIER)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_get_executor(), cls._load_local_model)
            log.info("stt.warmed")

    @classmethod
    def _load_local_model(cls):
        global _faster_whisper_model
        if _faster_whisper_model is None:
            from faster_whisper import WhisperModel
            _faster_whisper_model = WhisperModel(
                "large-v3",
                device="cpu",
                compute_type="int8",
                num_workers=2,
            )
            log.info("stt.local_model_loaded")
        return _faster_whisper_model

    @classmethod
    async def transcribe(
        cls,
        audio_bytes: bytes,
        hint_language: Optional[str] = None,
        sample_rate: int = STT_SAMPLE_RATE,
    ) -> dict:
        """
        Transcribe PCM 16-bit mono audio.

        Returns:
            transcript, language, confidence, latency_ms
        """
        start = time.monotonic()

        if settings.MODEL_TIER in ("free", "balanced"):
            result = await cls._transcribe_groq(audio_bytes, hint_language, sample_rate)
        else:
            result = await cls._transcribe_local(audio_bytes, hint_language, sample_rate)

        result["latency_ms"] = int((time.monotonic() - start) * 1000)
        log.debug(
            "stt.transcribed",
            language=result["language"],
            latency_ms=result["latency_ms"],
            chars=len(result["transcript"]),
        )
        return result

    @classmethod
    async def _transcribe_groq(
        cls,
        audio_bytes: bytes,
        hint_language: Optional[str],
        sample_rate: int,
    ) -> dict:
        """Transcribe via Groq Whisper API with a valid WAV payload."""
        if not settings.GROQ_API_KEY:
            log.error("stt.groq_missing_api_key")
            return {"transcript": "", "language": "en", "confidence": 0.0}

        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        wav_bytes = pcm16_to_wav(audio_bytes, sample_rate=sample_rate)

        kwargs = {
            "file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            "model": settings.GROQ_STT_MODEL,
            "response_format": "verbose_json",
            "temperature": 0.0,
        }
        lang = hint_language or (settings.GROQ_STT_LANGUAGE or None)
        if lang in ("en", "hi"):
            kwargs["language"] = lang
            if lang == "en":
                kwargs["prompt"] = (
                    "English phone call. Customer speaking English. Loan follow-up conversation."
                )
            else:
                kwargs["prompt"] = "Hindi phone call. Customer speaking Hindi."

        try:
            transcript = await client.audio.transcriptions.create(**kwargs)
            text = ""
            language = "en"
            if hasattr(transcript, "text"):
                text = (transcript.text or "").strip()
                language = getattr(transcript, "language", None) or "en"
            elif isinstance(transcript, dict):
                text = (transcript.get("text") or "").strip()
                language = transcript.get("language") or "en"
            return {
                "transcript": text,
                "language": language,
                "confidence": 1.0,
            }
        except Exception as e:
            log.error("stt.groq_error", error=str(e))
            return {"transcript": "", "language": "en", "confidence": 0.0}

    @classmethod
    async def _transcribe_local(
        cls,
        audio_bytes: bytes,
        hint_language: Optional[str],
        sample_rate: int,
    ) -> dict:
        """Transcribe via local faster-whisper."""
        loop = asyncio.get_event_loop()

        def _run():
            import numpy as np
            model = cls._load_local_model()
            audio_array = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            segments, info = model.transcribe(
                audio_array,
                beam_size=5,
                language=hint_language or (settings.GROQ_STT_LANGUAGE or None),
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            text = " ".join(seg.text for seg in segments).strip()
            return {
                "transcript": text,
                "language": info.language,
                "confidence": info.language_probability,
            }

        try:
            return await loop.run_in_executor(_get_executor(), _run)
        except Exception as e:
            log.error("stt.local_error", error=str(e))
            return {"transcript": "", "language": "en", "confidence": 0.0}
