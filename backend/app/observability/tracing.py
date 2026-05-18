"""Structured trace context bound to call_sid."""
import contextvars
import uuid
from typing import Optional

import structlog

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
call_sid_var: contextvars.ContextVar[str] = contextvars.ContextVar("call_sid", default="")


def bind_call_context(call_sid: str) -> str:
    trace_id = uuid.uuid4().hex[:16]
    trace_id_var.set(trace_id)
    call_sid_var.set(call_sid)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(trace_id=trace_id, call_sid=call_sid)
    return trace_id


def clear_call_context() -> None:
    structlog.contextvars.clear_contextvars()
    trace_id_var.set("")
    call_sid_var.set("")
