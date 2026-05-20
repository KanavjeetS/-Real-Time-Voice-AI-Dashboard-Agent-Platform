"""
AI Calling Agent — Text-to-Speech Service

Providers:
- edge: Microsoft Edge TTS (fast, ~300–800 ms) — default for production
- kokoro: Local ONNX (high quality, slow on small CPU) — local dev fallback
"""
import asyncio
import hashlib
import subprocess
import time
import structlog

from app.core.config import settings

log = structlog.get_logger()
_kokoro_model = None
_executor = None
_phrase_cache: dict[str, bytes] = {}

_KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")

_EDGE_GREETING = "Hi, this is Priya. How are you today?"


def _get_executor():
    global _executor
    if _executor is None:
        from concurrent.futures import ThreadPoolExecutor
        _executor = ThreadPoolExecutor(
            max_workers=max(4, settings.MAX_CONCURRENT_CALLS),
            thread_name_prefix="tts_worker",
        )
    return _executor


class TTSService:

    @classmethod
    def _active_provider(cls) -> str:
        if settings.TTS_PROVIDER == "auto":
            return "edge" if settings.is_production else "kokoro"
        return settings.TTS_PROVIDER

    @classmethod
    async def warm_up(cls):
        provider = cls._active_provider()
        log.info("tts.warming_up", provider=provider)
        if provider == "kokoro":
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_get_executor(), cls._load_kokoro_model)
        elif provider == "edge":
            # Verify edge TTS works before accepting traffic (avoid 60s+ kokoro fallback).
            probe = await cls.synthesize("Hello.", "en", skip_cache=True)
            if not probe:
                log.error("tts.edge_warm_failed", hint="Check edge-tts version and outbound network")
                return
        # Pre-cache greeting (most common first utterance)
        key = cls._cache_key(_EDGE_GREETING, "en")
        if key not in _phrase_cache:
            _phrase_cache[key] = await cls.synthesize(_EDGE_GREETING, "en", skip_cache=True)
        log.info("tts.warmed", provider=provider)

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
        """Returns mulaw G.711 mono @ 8 kHz (Twilio-compatible)."""
        if not text.strip():
            return b""

        cache_key = cls._cache_key(text, language)
        if not skip_cache and cache_key in _phrase_cache:
            log.debug("tts.cache_hit", chars=len(text))
            return _phrase_cache[cache_key]

        start = time.monotonic()
        provider = cls._active_provider()

        try:
            if provider == "edge":
                audio_bytes = await cls._synthesize_edge(text, language)
            else:
                loop = asyncio.get_event_loop()
                voice = settings.TTS_VOICE_HINDI if language == "hi" else settings.TTS_VOICE_ENGLISH
                audio_bytes = await loop.run_in_executor(
                    _get_executor(),
                    lambda: cls._synthesize_kokoro_sync(text, voice),
                )
        except Exception as e:
            log.error("tts.synthesize_failed", provider=provider, error=str(e))
            if provider == "edge" and not settings.is_production:
                try:
                    loop = asyncio.get_event_loop()
                    voice = settings.TTS_VOICE_ENGLISH
                    audio_bytes = await loop.run_in_executor(
                        _get_executor(),
                        lambda: cls._synthesize_kokoro_sync(text, voice),
                    )
                except Exception as e2:
                    log.error("tts.kokoro_fallback_failed", error=str(e2))
                    return b""
            else:
                return b""

        latency = int((time.monotonic() - start) * 1000)
        log.info(
            "tts.synthesized",
            provider=provider,
            language=language,
            latency_ms=latency,
            bytes=len(audio_bytes),
        )

        if len(text) < 120:
            _phrase_cache[cache_key] = audio_bytes
        return audio_bytes

    @classmethod
    async def _synthesize_edge(cls, text: str, language: str) -> bytes:
        import edge_tts

        voice = (
            settings.TTS_EDGE_VOICE_HINDI if language == "hi" else settings.TTS_EDGE_VOICE_ENGLISH
        )
        communicate = edge_tts.Communicate(text, voice, rate="+8%")
        mp3 = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3.extend(chunk["data"])
        if not mp3:
            raise RuntimeError("edge-tts returned empty audio")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_get_executor(), cls._mp3_to_mulaw, bytes(mp3))

    @classmethod
    def _mp3_to_mulaw(cls, mp3_bytes: bytes) -> bytes:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                "-ar", "8000", "-ac", "1", "-f", "mulaw", "pipe:1",
            ],
            input=mp3_bytes,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            raise RuntimeError(f"ffmpeg mulaw conversion failed: {proc.stderr.decode()[:200]}")
        return proc.stdout

    @classmethod
    def _model_dir(cls):
        from pathlib import Path
        return Path(__file__).resolve().parents[2] / "models" / "kokoro"

    @classmethod
    def _ensure_kokoro_files(cls) -> tuple[str, str]:
        import urllib.request
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
    def _load_kokoro_model(cls):
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
    def _synthesize_kokoro_sync(cls, text: str, voice: str) -> bytes:
        import numpy as np
        import scipy.signal
        model = cls._load_kokoro_model()
        samples, sample_rate = model.create(text, voice=voice, speed=1.05, lang="en-us")
        target_rate = 8000
        if sample_rate != target_rate:
            num_samples = int(len(samples) * target_rate / sample_rate)
            samples = scipy.signal.resample(samples, num_samples)
        samples_int16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        return audioop_ulaw_encode(samples_int16.tobytes(), 2)


def audioop_ulaw_encode(data: bytes, width: int) -> bytes:
    try:
        import audioop
        return audioop.lin2ulaw(data, width)
    except ImportError:
        import numpy as np
        samples = np.frombuffer(data, dtype=np.int16)
        BIAS = 0x84
        CLIP = 32635
        exp_lut = [0, 0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3] + [4] * 16 + [5] * 16 + [6] * 64 + [7] * 128
        result = []
        for s in samples:
            sign = 0 if s >= 0 else 0x80
            s = min(abs(int(s)), CLIP)
            s += BIAS
            exponent = exp_lut[(s >> 7) & 0xFF]
            mantissa = (s >> (exponent + 3)) & 0x0F
            result.append(~(sign | (exponent << 4) | mantissa) & 0xFF)
        return bytes(result)
