"""Built-in defaults when the database is empty or unavailable."""

DEFAULT_AGENT_ID = "00000000-0000-0000-0000-000000000001"

DEFAULT_SYSTEM_PROMPT = """You are Priya, a loan follow-up agent on a live phone call.
Match the customer's language (English or Hindi). Never mention language barriers.
Every reply must be ONE short sentence, under 12 words. Be warm and direct."""

DEFAULT_AGENT = {
    "id": DEFAULT_AGENT_ID,
    "name": "AI Calling Agent",
    "description": "AI agent for loan follow-up and customer support calls",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "voice_english": "af_sarah",
    "voice_hindi": "af_sky",
    "language_mode": "auto",
}
