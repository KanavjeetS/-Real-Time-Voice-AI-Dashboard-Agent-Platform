"""Per-turn latency breakdown for dashboards and Prometheus."""
import time
from dataclasses import dataclass, field
from typing import Optional

from prometheus_client import Histogram

# Layer 1 pipeline latency (seconds)
STT_LATENCY = Histogram(
    "vahanai_stt_latency_seconds",
    "STT transcription latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
LLM_LATENCY = Histogram(
    "vahanai_llm_latency_seconds",
    "LLM orchestration latency",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)
TTS_LATENCY = Histogram(
    "vahanai_tts_latency_seconds",
    "TTS synthesis latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
TURN_TOTAL_LATENCY = Histogram(
    "vahanai_turn_total_latency_seconds",
    "End-to-end turn latency (STT+LLM+TTS)",
    buckets=(0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0),
)


@dataclass
class TurnLatency:
    call_sid: str
    turn_index: int
    stt_ms: int = 0
    llm_ms: int = 0
    tts_ms: int = 0
    orchestration_ms: int = 0
    total_ms: int = 0
    _started: float = field(default_factory=time.monotonic)

    def mark_stt(self, ms: int) -> None:
        self.stt_ms = ms
        STT_LATENCY.observe(ms / 1000.0)

    def mark_llm(self, ms: int) -> None:
        self.llm_ms = ms
        LLM_LATENCY.observe(ms / 1000.0)

    def mark_tts(self, ms: int) -> None:
        self.tts_ms = ms
        TTS_LATENCY.observe(ms / 1000.0)

    def finish(self) -> dict:
        self.total_ms = int((time.monotonic() - self._started) * 1000)
        TURN_TOTAL_LATENCY.observe(self.total_ms / 1000.0)
        return {
            "call_sid": self.call_sid,
            "turn_index": self.turn_index,
            "stt_ms": self.stt_ms,
            "llm_ms": self.llm_ms,
            "tts_ms": self.tts_ms,
            "orchestration_ms": self.orchestration_ms,
            "total_ms": self.total_ms,
        }


class LatencyAggregator:
    """Rolling in-memory latency stats for dashboard (last N turns)."""

    _recent: list[dict] = []
    _max = 200

    @classmethod
    def record(cls, breakdown: dict) -> None:
        cls._recent.append(breakdown)
        if len(cls._recent) > cls._max:
            cls._recent = cls._recent[-cls._max :]

    @classmethod
    def summary(cls) -> dict:
        if not cls._recent:
            return {
                "sample_count": 0,
                "avg_stt_ms": 0,
                "avg_llm_ms": 0,
                "avg_tts_ms": 0,
                "avg_total_ms": 0,
                "p95_total_ms": 0,
                "recent": [],
            }
        n = len(cls._recent)
        totals = sorted(r["total_ms"] for r in cls._recent)
        p95_idx = min(int(n * 0.95), n - 1)
        return {
            "sample_count": n,
            "avg_stt_ms": round(sum(r["stt_ms"] for r in cls._recent) / n),
            "avg_llm_ms": round(sum(r["llm_ms"] for r in cls._recent) / n),
            "avg_tts_ms": round(sum(r["tts_ms"] for r in cls._recent) / n),
            "avg_total_ms": round(sum(r["total_ms"] for r in cls._recent) / n),
            "p95_total_ms": totals[p95_idx],
            "recent": cls._recent[-10:],
        }
