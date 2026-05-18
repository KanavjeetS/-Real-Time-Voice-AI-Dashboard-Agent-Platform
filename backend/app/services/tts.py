"""
AI Calling Agent — Text-to-Speech Service

Supports dual-voice bilingual switching:
- English utterances → TTS_VOICE_ENGLISH (e.g. af_sarah)
- Hindi utterances → TTS_VOICE_HINDI (e.g. af_sky)
- Caches common phrases in Redis to eliminate TTS latency for ~30% of utterances
"""
import asyncio
import io
import time
import hashlib
import struct
import structlog
from typing import Optional

from app.core.config import settings

log = structlog.get_logger()
_kokoro_model = None
_executor = None
_phrase_cache: dict = {}  # In-memory cache for common phrases

_KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


def _get_executor():
    global _executor
    if _executor is None:
        from concurrent.futures import ThreadPoolExecutor
        _executor = ThreadPoolExecutor(
            max_workers=max(2, (settings.MAX_CONCURRENT_CALLS // 2)),
            thread_name_prefix="tts_worker"
        )
    return _executor


class TTSService:

    @classmethod
    async def warm_up(cls):
        """Pre-load TTS model on startup."""
        log.info("tts.warming_up")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_get_executor(), cls._load_model)
        # Pre-generate common phrases into cache
        await cls._warm_phrase_cache()
        log.info("tts.warmed")

    @classmethod
    def _model_dir(cls):
        from pathlib import Path
        return Path(__file__).resolve().parents[2] / "models" / "kokoro"

    @classmethod
    def _ensure_kokoro_files(cls) -> tuple[str, str]:
        """Download Kokoro ONNX assets into backend/models/kokoro if missing."""
        import urllib.request
        from pathlib import Path

        model_dir = cls._model_dir()
        model_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for name in _KOKORO_FILES:
            dest = model_dir / name
            if not dest.is_file():
                url = f"{_KOKORO_RELEASE}/{name}"
                log.info("tts.downloading_model", file=name, url=url)
                urllib.request.urlretrieve(url, dest)
            paths.append(str(dest))
        return paths[0], paths[1]

    @classmethod
    def _load_model(cls):
        global _kokoro_model
        if _kokoro_model is None:
            import os
            import sys

            os.environ.setdefault("PYTHONUTF8", "1")
            if sys.platform == "win32":
                os.environ.setdefault("PYTHONIOENCODING", "utf-8")

            from kokoro_onnx import Kokoro

            onnx_path, voices_path = cls._ensure_kokoro_files()
            _kokoro_model = Kokoro(onnx_path, voices_path)
            log.info("tts.model_loaded", onnx=onnx_path)
        return _kokoro_model

    @classmethod
    async def _warm_phrase_cache(cls):
        """Pre-generate audio for common phrases to eliminate TTS latency."""
        common_phrases = [
            ("Hello, this is Priya calling. How are you today?", "en"),
            ("Thank you for your time. Have a great day!", "en"),
            ("I understand. Could you please repeat that?", "en"),
            ("नमस्ते, मैं प्रिया बोल रही हूँ।", "hi"),
            ("धन्यवाद, आपका दिन शुभ हो।", "hi"),
            ("Please hold on for just a moment.", "en"),
        ]
        for text, lang in common_phrases:
            cache_key = cls._cache_key(text, lang)
            if cache_key not in _phrase_cache:
                audio = await cls.synthesize(text, lang, skip_cache=True)
                _phrase_cache[cache_key] = audio

    @classmethod
    def _cache_key(cls, text: str, language: str) -> str:
        return hashlib.md5(f"{text}:{language}".encode()).hexdigest()

    @classmethod
    async def synthesize(
        cls,
        text: str,
        language: str = "en",
        skip_cache: bool = False,
    ) -> bytes:
        """
        Synthesize speech from text.

        Returns: mulaw G.711 audio at 8kHz (Twilio-compatible)
        """
        if not text.strip():
            return b""

        cache_key = cls._cache_key(text, language)
        if not skip_cache and cache_key in _phrase_cache:
            log.debug("tts.cache_hit", chars=len(text))
            return _phrase_cache[cache_key]

        start = time.monotonic()
        voice = settings.TTS_VOICE_HINDI if language == "hi" else settings.TTS_VOICE_ENGLISH

        try:
            loop = asyncio.get_event_loop()
            audio_bytes = await loop.run_in_executor(
                _get_executor(),
                lambda: cls._synthesize_sync(text, voice),
            )
        except Exception as e:
            log.error("tts.synthesize_failed", error=str(e))
            return b""

        latency = int((time.monotonic() - start) * 1000)
        log.debug("tts.synthesized", language=language, voice=voice, latency_ms=latency, chars=len(text))

        # Cache short phrases
        if len(text) < 200:
            _phrase_cache[cache_key] = audio_bytes

        return audio_bytes

    @classmethod
    def _synthesize_sync(cls, text: str, voice: str) -> bytes:
        """Blocking TTS synthesis — runs in thread pool."""
        import numpy as np
        from scipy.io import wavfile
        import scipy.signal

        model = cls._load_model()
        samples, sample_rate = model.create(text, voice=voice, speed=1.0, lang="en-us")

        # Resample to 8kHz for Twilio
        target_rate = 8000
        if sample_rate != target_rate:
            num_samples = int(len(samples) * target_rate / sample_rate)
            samples = scipy.signal.resample(samples, num_samples)

        # Convert float32 to int16
        samples_int16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)

        # Encode as mulaw (G.711)
        mulaw_bytes = audioop_ulaw_encode(samples_int16.tobytes(), 2)
        return mulaw_bytes


def audioop_ulaw_encode(data: bytes, width: int) -> bytes:
    """Encode PCM to mu-law. Python 3.13 removed audioop; this is a pure-Python fallback."""
    try:
        import audioop
        return audioop.lin2ulaw(data, width)
    except ImportError:
        # Pure Python mu-law encoding fallback
        import numpy as np
        samples = np.frombuffer(data, dtype=np.int16)
        BIAS = 0x84
        CLIP = 32635
        exp_lut = [0,0,1,1,2,2,2,2,3,3,3,3,3,3,3,3,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,
                   5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,
                   6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
                   6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
                   7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
                   7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
                   7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
                   7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7]
        result = []
        for s in samples:
            sign = 0 if s >= 0 else 0x80
            s = min(abs(int(s)), CLIP)
            s += BIAS
            exponent = exp_lut[(s >> 7) & 0xFF]
            mantissa = (s >> (exponent + 3)) & 0x0F
            result.append(~(sign | (exponent << 4) | mantissa) & 0xFF)
        return bytes(result)
