"""
AI Calling Agent — Application Configuration
All settings sourced from environment variables.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    # Comma-separated or JSON array string (List[str] env vars break on Railway)
    CORS_ORIGINS: str = "http://localhost:3000"
    SECRET_KEY: str = ""

    # ── Twilio ────────────────────────────────
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_WEBHOOK_BASE_URL: str = "http://localhost:8000"
    DEFAULT_PHONE_REGION: str = "IN"  # IN | US — used when user omits country code

    # ── Groq ──────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_LLM_MODEL: str = "llama-3.1-8b-instant"
    GROQ_INTENT_MODEL: str = "llama-3.1-8b-instant"
    GROQ_STT_MODEL: str = "whisper-large-v3"
    # Empty = Whisper auto-detects language (bilingual support)
    GROQ_STT_LANGUAGE: str = ""
    DEEPGRAM_API_KEY: str = ""
    ENABLE_STREAMING_STT: bool = True
    STT_STREAM_ENDPOINTING_MS: int = 250

    # ── TTS ───────────────────────────────────
    TTS_PROVIDER: str = "edge"  # auto | edge | kokoro
    TTS_VOICE_ENGLISH: str = "af_sarah"
    TTS_VOICE_HINDI: str = "af_sky"
    TTS_EDGE_VOICE_ENGLISH: str = "en-IN-NeerjaNeural"
    TTS_EDGE_VOICE_HINDI: str = "hi-IN-SwaraNeural"
    TTS_SAMPLE_RATE: int = 8000

    # ── Database ──────────────────────────────
    DATABASE_URL: str = ""
    USE_DATABASE: bool = True  # FIXED: must default to True

    # ── Redis ─────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Models ────────────────────────────────
    MODEL_TIER: str = "free"  # free | balanced | full
    STARTUP_WARM_MODELS: bool = False

    # ── Integrations ─────────────────────────
    SLACK_WEBHOOK_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""

    # ── Performance ───────────────────────────
    MAX_CONCURRENT_CALLS: int = 10
    CALL_TIMEOUT_SECONDS: int = 300
    VAD_SILENCE_THRESHOLD_MS: int = 250
    VAD_MIN_UTTERANCE_BYTES: int = 1600
    LLM_MAX_RESPONSE_TOKENS: int = 40
    LOW_LATENCY_MODE: bool = True

    @property
    def cors_origins(self) -> List[str]:
        s = self.CORS_ORIGINS.strip()
        if s.startswith("["):
            import json
            return json.loads(s)
        return [o.strip() for o in s.split(",") if o.strip()]

    @property
    def groq_intent_model(self) -> str:
        return self.GROQ_INTENT_MODEL or self.GROQ_LLM_MODEL

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def db_configured(self) -> bool:
        return bool(self.DATABASE_URL) and self.USE_DATABASE


settings = Settings()
