"""
AI Calling Agent — LLM Orchestration Service

- Uses Groq Llama for fast inference (<600ms TTFT)
- Intent classification on every turn
- Language-aware: responds in same language as caller
- Retry logic for Groq 429 rate limits
"""
import asyncio
import time
import structlog
from typing import Optional
from app.core.config import settings

log = structlog.get_logger()

INTENT_LABELS = {
    "interested": "Customer is interested in the loan product",
    "confused": "Customer is confused and needs clarification",
    "angry": "Customer is frustrated or hostile",
    "spam_invalid": "Wrong number or not a valid lead",
    "high_ticket": "High-value lead — immediate escalation needed",
    "callback": "Customer wants a callback at a different time",
    "not_interested": "Customer has clearly declined",
    "neutral": "No strong signal yet",
}

INTENT_ACTIONS = {
    "interested": "continue_and_qualify",
    "confused": "clarify_and_simplify",
    "angry": "de_escalate_and_offer_callback",
    "spam_invalid": "end_call_gracefully",
    "high_ticket": "escalate_to_human",
    "callback": "book_callback_slot",
    "not_interested": "thank_and_end",
    "neutral": "continue",
}


class LLMService:
    """Groq-based LLM with retry, intent classification, and bilingual support."""

    @classmethod
    async def generate_response(
        cls,
        messages: list[dict],
        system_prompt: str,
        detected_language: str = "en",
        max_tokens: int = 150,
        skip_intent_classification: bool = False,
    ) -> dict:
        """
        Generate conversational response.

        Returns:
            {
                "response": str,
                "intent": str,
                "latency_ms": int,
            }
        """
        start = time.monotonic()

        # Add language instruction to system prompt
        lang_instruction = cls._language_instruction(detected_language)
        full_system = f"{system_prompt}\n\n{lang_instruction}"

        response_text = await cls._call_groq_with_retry(
            messages=messages,
            system_prompt=full_system,
            max_tokens=max_tokens,
        )

        # Classify intent from latest user utterance
        user_text = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_text = msg["content"]
                break

        intent = "neutral"
        if not skip_intent_classification:
            intent = await cls._classify_intent(user_text, detected_language)
        latency_ms = int((time.monotonic() - start) * 1000)

        log.debug("llm.response_generated",
                  intent=intent,
                  latency_ms=latency_ms,
                  language=detected_language)

        return {
            "response": response_text,
            "intent": intent,
            "intent_action": INTENT_ACTIONS.get(intent, "continue"),
            "latency_ms": latency_ms,
        }

    @classmethod
    async def classify_intent_with_confidence(cls, user_text: str, language: str) -> tuple[str, float]:
        """Return (intent_label, confidence 0-1)."""
        if not settings.GROQ_API_KEY or not user_text.strip():
            return "neutral", 0.5

        prompt = f"""Classify intent. Reply with exactly two lines:
Line1: one label from [{', '.join(INTENT_LABELS.keys())}]
Line2: confidence score 0.0 to 1.0

Utterance: "{user_text}"
Language: {language}"""

        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.groq_intent_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=20,
                    temperature=0.0,
                ),
                timeout=3.0,
            )
            lines = response.choices[0].message.content.strip().splitlines()
            label = lines[0].strip().lower().split()[0] if lines else "neutral"
            if label not in INTENT_LABELS:
                label = "neutral"
            confidence = 0.7
            if len(lines) > 1:
                try:
                    confidence = float(lines[1].strip().split()[-1])
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass
            return label, confidence
        except Exception:
            label = await cls._classify_intent(user_text, language)
            return label, 0.65

    @classmethod
    async def generate_call_summary(cls, transcript_lines: list[str], language: str) -> str:
        """Post-call summary for CRM (Layer 3)."""
        if not settings.GROQ_API_KEY or not transcript_lines:
            return ""
        body = "\n".join(transcript_lines[-30:])
        prompt = f"""Summarize this phone call in 3-4 bullet points for a loan sales CRM.
Include: outcome, interest level, objections, next action.
Language of summary: English.

Transcript:
{body}"""
        return await cls._call_groq_with_retry(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a concise CRM analyst.",
            max_tokens=200,
        )

    @classmethod
    def _language_instruction(cls, language: str) -> str:
        if language == "hi":
            return (
                "LANGUAGE: Customer is using Hindi. Reply ONLY in Hindi (Devanagari). "
                "Do not mention language barriers."
            )
        return (
            "LANGUAGE: Customer is using English. Reply ONLY in English. "
            "Do not mention language barriers, translation, or switching languages."
        )

    @classmethod
    async def _call_groq_with_retry(
        cls,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int = 150,
        retries: int = 3,
        temperature: float = 0.7,
        timeout: float = 10.0,
    ) -> str:
        """Call Groq with exponential backoff on 429 rate limits."""
        from groq import AsyncGroq, RateLimitError

        if not settings.GROQ_API_KEY:
            log.error("llm.missing_api_key")
            return "I apologize, I'm having a technical issue. Could you please hold for a moment?"

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        last_error = None

        for attempt in range(retries):
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=settings.GROQ_LLM_MODEL,
                        messages=[{"role": "system", "content": system_prompt}] + messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stream=False,
                    ),
                    timeout=timeout,
                )
                return response.choices[0].message.content.strip()

            except RateLimitError as e:
                wait = 2 ** attempt
                log.warning("llm.rate_limited", attempt=attempt, wait_s=wait)
                await asyncio.sleep(wait)
                last_error = e

            except asyncio.TimeoutError:
                log.error("llm.timeout", attempt=attempt)
                last_error = TimeoutError("Groq LLM timed out")

            except Exception as e:
                log.error("llm.error", error=str(e), attempt=attempt)
                last_error = e
                break

        log.error("llm.failed_all_retries", error=str(last_error))
        return "I apologize, I'm having a technical issue. Could you please hold for a moment?"

    @classmethod
    async def _classify_intent(cls, user_text: str, language: str) -> str:
        """Classify caller intent from utterance text."""
        if not settings.GROQ_API_KEY:
            return "neutral"
        if not user_text.strip():
            return "neutral"

        prompt = f"""Classify the caller's intent from this utterance into exactly ONE of these labels:
{chr(10).join(f'- {k}: {v}' for k, v in INTENT_LABELS.items())}

Utterance: "{user_text}"
Language: {language}

Respond with ONLY the label name, nothing else."""

        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.groq_intent_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                    temperature=0.0,
                ),
                timeout=3.0
            )
            label = response.choices[0].message.content.strip().lower()
            return label if label in INTENT_LABELS else "neutral"
        except Exception:
            return "neutral"

    @classmethod
    async def generate_turn_combined(
        cls,
        conversation_history: list[dict],
        system_prompt: str,
        language: str,
        max_tokens: int = 40,
    ) -> dict:
        """
        Single fast Groq call: intent + short spoken reply (saves ~400–700 ms vs two calls).
        """
        from app.utils.voice import truncate_for_voice

        labels = ", ".join(INTENT_LABELS.keys())
        actions = ", ".join(sorted(set(INTENT_ACTIONS.values())))
        lang_name = "Hindi (Devanagari)" if language == "hi" else "English"
        compact_system = f"""{system_prompt}

Live phone call. Customer language: {lang_name}.
Real-time loan assistant responsibilities:
- greeting, eligibility inquiry, EMI clarification, document reminder
- objection handling, callback booking, escalation on hot leads
Reply in ONE short spoken sentence (max 12 words). No preamble.

Reply format (exactly three lines):
INTENT: <one of {labels}>
ACTION: <one of {actions}>
SAY: <spoken reply>

Never output extra lines or commentary."""

        start = time.monotonic()
        raw = await cls._call_groq_with_retry(
            messages=conversation_history[-6:],
            system_prompt=compact_system,
            max_tokens=max_tokens,
            temperature=0.5,
            timeout=4.0,
            retries=2,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        intent = "neutral"
        intent_action = INTENT_ACTIONS.get(intent, "continue")
        response = raw.strip()
        for line in raw.splitlines():
            upper = line.strip().upper()
            if upper.startswith("INTENT:"):
                label = line.split(":", 1)[1].strip().lower().split()[0]
                if label in INTENT_LABELS:
                    intent = label
                    intent_action = INTENT_ACTIONS.get(intent, "continue")
            elif upper.startswith("ACTION:"):
                action = line.split(":", 1)[1].strip().lower().replace(" ", "_")
                if action in INTENT_ACTIONS.values():
                    intent_action = action
            elif upper.startswith("SAY:"):
                response = line.split(":", 1)[1].strip()

        response = truncate_for_voice(response)
        log.info("llm.turn_combined", intent=intent, latency_ms=latency_ms, chars=len(response))
        return {
            "response": response,
            "intent": intent,
            "intent_action": intent_action,
            "intent_confidence": 0.75,
            "latency_ms": latency_ms,
        }
