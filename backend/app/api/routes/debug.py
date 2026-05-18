"""AI Calling Agent — Debug Endpoints (non-production only)"""
from fastapi import APIRouter, Query
from app.core.config import settings

router = APIRouter()


@router.get("/stt-test")
async def stt_test():
    """Test STT with synthetic speech-like audio at telephony sample rate (8 kHz)."""
    import numpy as np
    from app.services.stt import STTService, STT_SAMPLE_RATE
    from app.utils.audio import pcm16_to_wav

    # 1.5 s tone burst — validates WAV wrapping + Groq API connectivity
    duration_s = 1.5
    t = np.linspace(0, duration_s, int(STT_SAMPLE_RATE * duration_s), dtype=np.float32)
    samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
    audio_bytes = samples.tobytes()

    result = await STTService.transcribe(audio_bytes, sample_rate=STT_SAMPLE_RATE)
    return {
        "status": "ok" if settings.GROQ_API_KEY else "missing_api_key",
        "model": settings.GROQ_STT_MODEL,
        "sample_rate_hz": STT_SAMPLE_RATE,
        "wav_bytes": len(pcm16_to_wav(audio_bytes, sample_rate=STT_SAMPLE_RATE)),
        "result": result,
    }


@router.get("/llm-test")
async def llm_test():
    """Test LLM + intent classification."""
    from app.services.llm import LLMService

    if not settings.GROQ_API_KEY:
        return {"status": "missing_api_key", "model": settings.GROQ_LLM_MODEL}

    result = await LLMService.generate_response(
        messages=[{"role": "user", "content": "Hello, I'm calling about my loan application."}],
        system_prompt="You are a loan follow-up agent named Priya.",
        detected_language="en",
    )
    return {
        "status": "ok",
        "model": settings.GROQ_LLM_MODEL,
        "intent_model": settings.groq_intent_model,
        "result": result,
    }


@router.get("/tts-test")
async def tts_test(text: str = Query(default="Hello, this is a test of the voice system.")):
    """Test TTS pipeline — returns audio length."""
    from app.services.tts import TTSService

    audio_bytes = await TTSService.synthesize(text, language="en")
    return {
        "status": "ok",
        "audio_bytes": len(audio_bytes),
        "duration_ms": int(len(audio_bytes) / 8),
        "voice": settings.TTS_VOICE_ENGLISH,
    }


@router.get("/providers")
async def provider_status():
    """Check status of all configured providers."""
    return {
        "groq": bool(settings.GROQ_API_KEY),
        "groq_llm_model": settings.GROQ_LLM_MODEL,
        "groq_stt_model": settings.GROQ_STT_MODEL,
        "twilio": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN),
        "database": settings.db_configured,
        "redis": bool(settings.REDIS_URL),
        "slack": bool(settings.SLACK_WEBHOOK_URL),
        "model_tier": settings.MODEL_TIER,
    }


@router.get("/smoke-test")
async def smoke_test():
    """Run LLM + STT quick checks and return a single pass/fail summary."""
    from app.services.llm import LLMService
    from app.services.stt import STTService, STT_SAMPLE_RATE
    import numpy as np

    checks: dict = {}

    if not settings.GROQ_API_KEY:
        checks["groq_api_key"] = False
        return {"status": "fail", "checks": checks, "message": "GROQ_API_KEY not set"}

    checks["groq_api_key"] = True

    llm = await LLMService.generate_response(
        messages=[{"role": "user", "content": "Say hello in one short sentence."}],
        system_prompt="You are a helpful assistant.",
        detected_language="en",
        max_tokens=40,
    )
    checks["llm"] = bool(llm.get("response") and "technical issue" not in llm["response"].lower())

    t = np.linspace(0, 1.0, STT_SAMPLE_RATE, dtype=np.float32)
    pcm = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16).tobytes()
    stt = await STTService.transcribe(pcm, sample_rate=STT_SAMPLE_RATE)
    checks["stt_api"] = stt.get("latency_ms", 0) > 0 and stt.get("confidence", 0) >= 0

    all_ok = all(checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks, "llm_preview": llm.get("response", "")[:120]}
