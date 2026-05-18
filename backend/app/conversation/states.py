"""Dialogue state machine for loan follow-up voice agents."""
from enum import Enum


class DialogueState(str, Enum):
    GREETING = "greeting"
    QUALIFY = "qualify"
    HANDLE_OBJECTION = "handle_objection"
    BOOK_CALLBACK = "book_callback"
    DE_ESCALATE = "de_escalate"
    ESCALATE = "escalate"
    CLOSE = "close"


# Allowed transitions: current -> set of next states
TRANSITIONS: dict[DialogueState, set[DialogueState]] = {
    DialogueState.GREETING: {
        DialogueState.QUALIFY,
        DialogueState.HANDLE_OBJECTION,
        DialogueState.CLOSE,
    },
    DialogueState.QUALIFY: {
        DialogueState.QUALIFY,
        DialogueState.HANDLE_OBJECTION,
        DialogueState.BOOK_CALLBACK,
        DialogueState.DE_ESCALATE,
        DialogueState.ESCALATE,
        DialogueState.CLOSE,
    },
    DialogueState.HANDLE_OBJECTION: {
        DialogueState.QUALIFY,
        DialogueState.BOOK_CALLBACK,
        DialogueState.CLOSE,
    },
    DialogueState.BOOK_CALLBACK: {DialogueState.CLOSE, DialogueState.QUALIFY},
    DialogueState.DE_ESCALATE: {DialogueState.QUALIFY, DialogueState.BOOK_CALLBACK, DialogueState.CLOSE},
    DialogueState.ESCALATE: {DialogueState.CLOSE},
    DialogueState.CLOSE: {DialogueState.CLOSE},
}


def can_transition(from_state: DialogueState, to_state: DialogueState) -> bool:
    return to_state in TRANSITIONS.get(from_state, set())
