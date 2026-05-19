"""Helpers for low-latency voice responses."""


def truncate_for_voice(text: str, max_words: int = 12) -> str:
    """Keep TTS input short — first sentence, capped word count."""
    text = (text or "").strip()
    if not text:
        return text
    for sep in (". ", "? ", "! ", "। "):
        idx = text.find(sep)
        if idx != -1:
            text = text[: idx + len(sep.rstrip())]
            break
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(",;:")
        if text and text[-1] not in ".?!":
            text += "."
    return text
