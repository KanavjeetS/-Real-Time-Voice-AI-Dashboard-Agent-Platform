"""Escalation policies with intent confidence thresholds."""
from dataclasses import dataclass

from app.conversation.states import DialogueState


@dataclass
class EscalationDecision:
    escalate: bool
    new_state: DialogueState | None
    reason: str
    notify_slack: bool = False
    end_call: bool = False


class EscalationPolicy:
    """
    Production escalation rules:
    - High-ticket + confidence → Slack + continue qualify
    - Angry + high confidence → de-escalate first
    - Angry + repeated → human escalate
    - Spam → graceful end
    """

    ANGRY_THRESHOLD = 2
    NOT_INTERESTED_THRESHOLD = 2
    HIGH_CONFIDENCE = 0.75

    @classmethod
    def evaluate(
        cls,
        intent: str,
        confidence: float,
        memory_not_interested: int,
        memory_angry_turns: int,
    ) -> EscalationDecision:
        if intent == "spam_invalid" and confidence >= 0.6:
            return EscalationDecision(
                escalate=False,
                new_state=DialogueState.CLOSE,
                reason="invalid_lead",
                end_call=True,
            )

        if intent == "high_ticket" and confidence >= cls.HIGH_CONFIDENCE:
            return EscalationDecision(
                escalate=True,
                new_state=DialogueState.QUALIFY,
                reason="high_value_lead",
                notify_slack=True,
            )

        if intent == "angry":
            if memory_angry_turns >= cls.ANGRY_THRESHOLD:
                return EscalationDecision(
                    escalate=True,
                    new_state=DialogueState.ESCALATE,
                    reason="repeated_hostility",
                    notify_slack=True,
                    end_call=True,
                )
            return EscalationDecision(
                escalate=False,
                new_state=DialogueState.DE_ESCALATE,
                reason="first_hostility",
            )

        if intent == "not_interested" and memory_not_interested >= cls.NOT_INTERESTED_THRESHOLD:
            return EscalationDecision(
                escalate=False,
                new_state=DialogueState.CLOSE,
                reason="clear_decline",
                end_call=True,
            )

        if intent == "callback":
            return EscalationDecision(
                escalate=False,
                new_state=DialogueState.BOOK_CALLBACK,
                reason="callback_requested",
            )

        return EscalationDecision(escalate=False, new_state=None, reason="continue")
