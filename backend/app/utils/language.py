"""
Conversation language detection — prefer transcript script over Whisper locale tags.

Indian English is often mis-tagged as Hindi by Whisper; Latin-script utterances should stay English.
"""
from __future__ import annotations

import re

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN_WORD = re.compile(r"[a-zA-Z]{2,}")


def _normalize_whisper_lang(lang: str | None) -> str:
    l = (lang or "en").lower().strip()
    if l.startswith("hi") or l in ("hin", "hindi"):
        return "hi"
    if l.startswith("en") or l in ("eng", "english"):
        return "en"
    return "en"


def language_from_transcript(text: str) -> str | None:
    """Infer language from what was actually said (most reliable for phone STT)."""
    if not text or not text.strip():
        return None

    devanagari_chars = len(_DEVANAGARI.findall(text))
    latin_words = len(_LATIN_WORD.findall(text))

    if devanagari_chars >= 2:
        if latin_words >= 2 and devanagari_chars < latin_words:
            return "en"  # Hinglish — default to English for TTS clarity unless mostly Devanagari
        return "hi"

    if latin_words >= 1 or re.search(r"[a-zA-Z]", text):
        return "en"

    return None


def resolve_conversation_language(
    transcript: str,
    whisper_language: str | None,
    session_language: str = "en",
) -> str:
    """
    Pick the language the agent should use for this turn.
    Transcript beats Whisper; session preference breaks ties.
    """
    from_text = language_from_transcript(transcript)
    if from_text:
        return from_text

    whisper = _normalize_whisper_lang(whisper_language)
    if whisper == "hi" and language_from_transcript(transcript) is None:
        # Whisper said Hindi but no Devanagari — treat as English (common with Indian accent).
        if re.search(r"[a-zA-Z]{3,}", transcript or ""):
            return "en"

    if whisper in ("en", "hi"):
        return whisper

    return _normalize_whisper_lang(session_language)
