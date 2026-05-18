"""Per-call memory: slots, objection history, turn context (Redis-backed)."""
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import structlog

from app.core.config import settings

log = structlog.get_logger()

MEMORY_TTL_SECONDS = 3600


@dataclass
class ConversationMemory:
    call_sid: str
    dialogue_state: str = "greeting"
    lead_name: Optional[str] = None
    loan_amount: Optional[str] = None
    callback_time: Optional[str] = None
    objections_raised: list[str] = field(default_factory=list)
    not_interested_count: int = 0
    turn_count: int = 0
    facts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMemory":
        return cls(
            call_sid=data.get("call_sid", ""),
            dialogue_state=data.get("dialogue_state", "greeting"),
            lead_name=data.get("lead_name"),
            loan_amount=data.get("loan_amount"),
            callback_time=data.get("callback_time"),
            objections_raised=list(data.get("objections_raised") or []),
            not_interested_count=int(data.get("not_interested_count") or 0),
            turn_count=int(data.get("turn_count") or 0),
            facts=dict(data.get("facts") or {}),
        )

    def context_block(self) -> str:
        """Compact memory block injected into the LLM system prompt."""
        lines = [
            f"Dialogue state: {self.dialogue_state}",
            f"Turn: {self.turn_count}",
        ]
        if self.lead_name:
            lines.append(f"Customer name: {self.lead_name}")
        if self.loan_amount:
            lines.append(f"Loan interest: {self.loan_amount}")
        if self.callback_time:
            lines.append(f"Callback requested: {self.callback_time}")
        if self.objections_raised:
            lines.append(f"Objections already handled: {', '.join(self.objections_raised[-3:])}")
        return "\n".join(lines)


class MemoryStore:
    """Persist conversation memory in Redis (fallback: in-process)."""

    _local: dict[str, ConversationMemory] = {}

    @classmethod
    def _key(cls, call_sid: str) -> str:
        return f"vahanai:call:{call_sid}:memory"

    @classmethod
    async def load(cls, call_sid: str) -> ConversationMemory:
        try:
            from app.db.redis_client import get_redis
            redis = await get_redis()
            raw = await redis.get(cls._key(call_sid))
            if raw:
                return ConversationMemory.from_dict(json.loads(raw))
        except Exception as e:
            log.debug("memory.redis_miss", error=str(e))
        if call_sid in cls._local:
            return cls._local[call_sid]
        mem = ConversationMemory(call_sid=call_sid)
        cls._local[call_sid] = mem
        return mem

    @classmethod
    async def save(cls, memory: ConversationMemory) -> None:
        cls._local[memory.call_sid] = memory
        try:
            from app.db.redis_client import get_redis
            redis = await get_redis()
            await redis.setex(
                cls._key(memory.call_sid),
                MEMORY_TTL_SECONDS,
                json.dumps(memory.to_dict()),
            )
        except Exception as e:
            log.debug("memory.redis_save_skip", error=str(e))

    @classmethod
    async def delete(cls, call_sid: str) -> None:
        cls._local.pop(call_sid, None)
        try:
            from app.db.redis_client import get_redis
            redis = await get_redis()
            await redis.delete(cls._key(call_sid))
        except Exception:
            pass
