"""
AI Calling Agent — Application Configuration
All settings sourced from environment variables.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


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
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    SECRET_KEY: str = ""

    # ── Twilio ────────────────────────────────
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_WEBHOOK_BASE_URL: str = "http://localhost:8000"
    DEFAULT_PHONE_REGION: str = "IN"  # IN | US — used when user omits country code

    # ── Groq ──────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_LLM_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_INTENT_MODEL: str = "llama-3.1-8b-instant"  # fast intent; empty = use GROQ_LLM_MODEL
    GROQ_STT_MODEL: str = "whisper-large-v3"
    # Empty = Whisper auto-detects language (bilingual support)
    GROQ_STT_LANGUAGE: str = ""

    # ── TTS ───────────────────────────────────
    TTS_PROVIDER: str = "kokoro"
    TTS_VOICE_ENGLISH: str = "af_sarah"
    TTS_VOICE_HINDI: str = "af_sky"
    TTS_SAMPLE_RATE: int = 8000

    # ── Database ──────────────────────────────
    DATABASE_URL: str = ""
    USE_DATABASE: bool = True  # FIXED: must default to True

    # ── Redis ─────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Models ────────────────────────────────
    MODEL_TIER: str = "free"  # free | balanced | full
    STARTUP_WARM_MODELS: bool = True

    # ── Integrations ─────────────────────────
    SLACK_WEBHOOK_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""

    # ── Performance ───────────────────────────
    MAX_CONCURRENT_CALLS: int = 10
    CALL_TIMEOUT_SECONDS: int = 300
    VAD_SILENCE_THRESHOLD_MS: int = 350
    VAD_MIN_UTTERANCE_BYTES: int = 2400
    LLM_MAX_RESPONSE_TOKENS: int = 80

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                import json
                return json.loads(s)
            return [o.strip() for o in s.split(",") if o.strip()]
        return v

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
