"""
Layer 2 — Advanced Conversation Engine

Replaces naive STT → LLM → TTS with:
- State machine transitions
- Redis-backed memory
- Objection flows
- Intent confidence
- Escalation policies
"""
import re
import time
import asyncio
from dataclasses import dataclass
from typing import Optional

import structlog

from app.core.config import settings
from app.conversation.escalation import EscalationPolicy
from app.conversation.memory import ConversationMemory, MemoryStore
from app.conversation.objections import detect_objection, objection_prompt
from app.conversation.states import DialogueState, can_transition
from app.services.llm import LLMService, INTENT_ACTIONS
from app.observability.latency import TurnLatency

log = structlog.get_logger()


@dataclass
class OrchestratorResult:
    response: str
    intent: str
    intent_confidence: float
    intent_action: str
    dialogue_state: str
    should_end_call: bool
    notify_slack: bool
    objection_key: Optional[str] = None
    lead_score: float = 0.0
    latency_ms: int = 0


class ConversationOrchestrator:
    """Structured dialogue orchestration for a single voice turn."""

    @classmethod
    async def process_turn(
        cls,
        call_sid: str,
        turn_index: int,
        user_text: str,
        language: str,
        conversation_history: list[dict],
        system_prompt: str,
        latency: TurnLatency,
    ) -> OrchestratorResult:
        orch_start = time.monotonic()
        memory_task = asyncio.create_task(MemoryStore.load(call_sid))

        if settings.LOW_LATENCY_MODE:
            memory = await memory_task
            memory.turn_count += 1
            llm_result = await LLMService.generate_turn_combined(
                conversation_history=conversation_history,
                system_prompt=system_prompt,
                language=language,
                max_tokens=settings.LLM_MAX_RESPONSE_TOKENS,
            )
            llm_ms = llm_result["latency_ms"]
            latency.mark_llm(llm_ms)
            intent = llm_result["intent"]
            confidence = llm_result["intent_confidence"]
            response_text = llm_result["response"]
        else:
            memory = await memory_task
            memory.turn_count += 1
            intent, confidence = await LLMService.classify_intent_with_confidence(user_text, language)
            latency.orchestration_ms = int((time.monotonic() - orch_start) * 1000)
            response_text = None  # filled by full LLM path below

        angry_turns = memory.facts.get("angry_turns", 0)
        if intent == "angry":
            angry_turns += 1
            memory.facts["angry_turns"] = angry_turns

        if intent == "not_interested":
            memory.not_interested_count += 1

        objection = detect_objection(user_text, language)
        if objection and objection.key not in memory.objections_raised:
            memory.objections_raised.append(objection.key)

        new_state = cls._next_state(
            memory=memory,
            intent=intent,
            confidence=confidence,
            objection_key=objection.key if objection else None,
        )
        if can_transition(DialogueState(memory.dialogue_state), new_state):
            memory.dialogue_state = new_state.value
        else:
            memory.dialogue_state = new_state.value

        escalation = EscalationPolicy.evaluate(
            intent=intent,
            confidence=confidence,
            memory_not_interested=memory.not_interested_count,
            memory_angry_turns=angry_turns,
        )
        if escalation.new_state:
            memory.dialogue_state = escalation.new_state.value

        cls._extract_slots(memory, user_text, language)

        if not settings.LOW_LATENCY_MODE:
            state_guidance = cls._state_guidance(DialogueState(memory.dialogue_state), language)
            objection_guidance = objection_prompt(objection, language) if objection else ""

            augmented_system = f"""{system_prompt}

--- CONVERSATION ORCHESTRATION ---
{memory.context_block()}
{state_guidance}
{f"OBJECTION HANDLING: {objection_guidance}" if objection_guidance else ""}
Detected intent: {intent} (confidence {confidence:.2f})
Rules:
- Stay in dialogue state; use controlled transitions only.
- Customer language for this turn: {language} (en=English only, hi=Hindi only). Never mention language barriers.
- Max 1-2 short sentences (phone call). Be brief.
- If customer interrupted you, acknowledge briefly first.
"""

            llm_start = time.monotonic()
            llm_result = await LLMService.generate_response(
                messages=conversation_history,
                system_prompt=augmented_system,
                detected_language=language,
                max_tokens=settings.LLM_MAX_RESPONSE_TOKENS,
                skip_intent_classification=True,
            )
            llm_ms = int((time.monotonic() - llm_start) * 1000)
            latency.mark_llm(llm_ms)
            response_text = llm_result["response"]
        else:
            llm_ms = llm_result["latency_ms"]

        lead_score = cls._compute_lead_score(intent, confidence, memory)

        await MemoryStore.save(memory)

        intent_action = INTENT_ACTIONS.get(intent, "continue")
        should_end = escalation.end_call or intent_action in ("end_call_gracefully", "thank_and_end")

        return OrchestratorResult(
            response=response_text,
            intent=intent,
            intent_confidence=confidence,
            intent_action=intent_action,
            dialogue_state=memory.dialogue_state,
            should_end_call=should_end,
            notify_slack=escalation.notify_slack or intent in ("high_ticket", "interested"),
            objection_key=objection.key if objection else None,
            lead_score=lead_score,
            latency_ms=llm_ms,
        )

    @classmethod
    def _next_state(
        cls,
        memory: ConversationMemory,
        intent: str,
        confidence: float,
        objection_key: Optional[str],
    ) -> DialogueState:
        current = DialogueState(memory.dialogue_state)

        if current == DialogueState.GREETING:
            return DialogueState.QUALIFY

        if objection_key:
            return DialogueState.HANDLE_OBJECTION

        if intent == "callback":
            return DialogueState.BOOK_CALLBACK
        if intent == "angry":
            return DialogueState.DE_ESCALATE
        if intent == "high_ticket" and confidence >= 0.75:
            return DialogueState.ESCALATE
        if intent in ("not_interested", "spam_invalid"):
            return DialogueState.CLOSE
        if intent == "interested":
            return DialogueState.QUALIFY
        return current if current != DialogueState.GREETING else DialogueState.QUALIFY

    @classmethod
    def _state_guidance(cls, state: DialogueState, language: str) -> str:
        guides = {
            DialogueState.GREETING: "Warm greeting; confirm identity.",
            DialogueState.QUALIFY: "Ask about loan need, amount, timeline. One question at a time.",
            DialogueState.HANDLE_OBJECTION: "Empathize first; address objection; do not push aggressively.",
            DialogueState.BOOK_CALLBACK: "Confirm date/time; repeat back; thank them.",
            DialogueState.DE_ESCALATE: "Lower pace; apologize for frustration; offer supervisor callback.",
            DialogueState.ESCALATE: "Inform human specialist will follow up within 24 hours.",
            DialogueState.CLOSE: "Thank them; polite goodbye; no new questions.",
        }
        base = guides.get(state, "")
        if language == "hi":
            return base + " Respond in Hindi (Devanagari) unless customer mixes Hinglish."
        return base + " Respond in clear professional English."

    @classmethod
    def _extract_slots(cls, memory: ConversationMemory, text: str, language: str) -> None:
        lower = text.lower()
        amount_match = re.search(r"(\d[\d,\.]*)\s*(lakh|lac|crore|k|thousand)?", lower, re.I)
        if amount_match and not memory.loan_amount:
            memory.loan_amount = amount_match.group(0)
        if "call me" in lower or "बाद में" in text:
            memory.callback_time = text[:80]

    @classmethod
    def _compute_lead_score(cls, intent: str, confidence: float, memory: ConversationMemory) -> float:
        score = 0.2
        weights = {
            "high_ticket": 0.95,
            "interested": 0.85,
            "callback": 0.65,
            "confused": 0.45,
            "neutral": 0.35,
            "not_interested": 0.1,
            "angry": 0.15,
            "spam_invalid": 0.0,
        }
        score = weights.get(intent, 0.3) * max(confidence, 0.5)
        if memory.loan_amount:
            score = min(1.0, score + 0.1)
        if memory.callback_time:
            score = min(1.0, score + 0.05)
        return round(score, 3)
