"""Objection detection and scripted recovery flows (bilingual)."""
from dataclasses import dataclass


@dataclass
class ObjectionFlow:
    key: str
    triggers_en: tuple[str, ...]
    triggers_hi: tuple[str, ...]
    guidance_en: str
    guidance_hi: str


OBJECTION_FLOWS: list[ObjectionFlow] = [
    ObjectionFlow(
        key="not_interested",
        triggers_en=("not interested", "don't call", "stop calling", "remove my number"),
        triggers_hi=("दिलचस्पी नहीं", "कॉल मत करो", "बंद करो"),
        guidance_en="Acknowledge respectfully. Ask one soft question about timing, then offer callback.",
        guidance_hi="सम्मान से स्वीकार करें। समय के बारे में एक हल्का सवाल पूछें, फिर कॉलबैक ऑफर करें।",
    ),
    ObjectionFlow(
        key="too_expensive",
        triggers_en=("too expensive", "rate is high", "emi is high", "cannot afford"),
        triggers_hi=("महंगा", "ब्याज ज्यादा", "ईएमआई ज्यादा"),
        guidance_en="Explain flexible tenure and EMI options. Offer to send a comparison summary.",
        guidance_hi="लचीली अवधि और EMI विकल्प समझाएं। तुलना सारांश भेजने की पेशकश करें।",
    ),
    ObjectionFlow(
        key="already_have_loan",
        triggers_en=("already have a loan", "already took", "got elsewhere"),
        triggers_hi=("पहले से लोन", "ले लिया", "कहीं और से"),
        guidance_en="Congratulate them. Ask if top-up or balance transfer could help.",
        guidance_hi="बधाई दें। पूछें कि टॉप-अप या बैलेंस ट्रांसफर मदद कर सकता है या नहीं।",
    ),
    ObjectionFlow(
        key="need_time",
        triggers_en=("call me later", "busy now", "in a meeting"),
        triggers_hi=("बाद में कॉल", "अभी व्यस्त", "मीटिंग में"),
        guidance_en="Confirm preferred callback window. Repeat it back for accuracy.",
        guidance_hi="पसंदीदा कॉलबैक समय की पुष्टि करें। सटीकता के लिए दोहराएं।",
    ),
]


def detect_objection(text: str, language: str) -> ObjectionFlow | None:
    lower = text.lower()
    for flow in OBJECTION_FLOWS:
        triggers = flow.triggers_hi if language == "hi" else flow.triggers_en
        if any(t in lower for t in triggers):
            return flow
    return None


def objection_prompt(flow: ObjectionFlow, language: str) -> str:
    return flow.guidance_hi if language == "hi" else flow.guidance_en
