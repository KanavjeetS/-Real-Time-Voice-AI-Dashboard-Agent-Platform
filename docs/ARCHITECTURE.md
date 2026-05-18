# AI Calling Agent — 4-Layer Architecture

## Overview

AI Calling Agent is structured as four composable layers for production voice agents (loan follow-up / bilingual support).

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4 — Scalability                                          │
│  Redis job queue · background workers · Prometheus · tracing    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3 — Enterprise                                           │
│  CRM · lead scoring · call summaries · Slack · dashboard          │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2 — Agentic Intelligence                                 │
│  State machine · memory · objections · escalation · confidence  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1 — Real-Time Voice Core                                 │
│  Twilio Media Streams · WebSocket · STT · TTS · barge-in        │
└─────────────────────────────────────────────────────────────────┘
```

## Layer 1 — Real-Time Voice Core

| Component | Implementation |
|-----------|----------------|
| Telephony | Twilio outbound + Media Streams |
| Transport | `WebSocket /api/v1/ws/twilio` |
| STT | Groq Whisper (`free` tier) or faster-whisper (`full`) |
| TTS | Kokoro ONNX → mulaw 8 kHz, 20 ms chunks |
| Barge-in | VAD energy + Twilio `clear` event |
| Interruption recovery | `[Customer interrupted]` prefix on next turn |

**Code:** `app/api/routes/ws_twilio.py`, `app/services/stt.py`, `app/services/tts.py`

## Layer 2 — Agentic Intelligence

Replaces naive `STT → LLM → TTS` with **ConversationOrchestrator**:

| Feature | Module |
|---------|--------|
| Dialogue states | `app/conversation/states.py` |
| Redis-backed memory | `app/conversation/memory.py` |
| Objection flows (EN/HI) | `app/conversation/objections.py` |
| Escalation policies | `app/conversation/escalation.py` |
| Orchestration | `app/conversation/orchestrator.py` |

**States:** `greeting` → `qualify` → `handle_objection` | `book_callback` | `de_escalate` | `escalate` | `close`

**Intent confidence:** `LLMService.classify_intent_with_confidence()` drives transitions and lead score.

## Layer 3 — Enterprise

| Feature | Implementation |
|---------|----------------|
| CRM writes | `CRMService` — calls, turns, finalize |
| Lead scoring | 0–1 score from intent + slots (`orchestrator._compute_lead_score`) |
| Call summaries | Post-call LLM summary via worker |
| Slack hot leads | Queue job on `high_ticket` / `interested` |
| Dashboard | Next.js + `/api/v1/dashboard/stats` |
| Analytics | `/api/v1/analytics/latency`, `/analytics/overview` |

## Layer 4 — Scalability

| Feature | Implementation |
|---------|----------------|
| Redis queue | `app/workers/queue.py` — `LPUSH` / `BRPOP` |
| Workers | `python backend/run_worker.py` (horizontally scalable) |
| Metrics | Prometheus histograms on `/metrics` |
| Tracing | `trace_id` + `call_sid` via structlog context |
| Latency breakdown | `app/observability/latency.py` |

### Job types

- `post_call_summary` — LLM CRM summary
- `lead_score_sync` — persist score to `calls.sentiment_score`
- `slack_alert` — async Slack webhook
- `crm_sync` — extension point for external CRM

## API Flow (Outbound Call)

```
Dashboard POST /calls/initiate
  → Twilio dials customer
  → POST /ws/twilio/twiml?agentId=...
  → WebSocket /ws/twilio
       → STT (8 kHz WAV)
       → ConversationOrchestrator
       → TTS streaming chunks
  → POST /calls/status (Twilio callbacks)
  → Worker: summary + lead score
```

## Demo Scenarios

| Scenario | How to trigger |
|----------|----------------|
| English qualify | Answer in English, discuss loan amount |
| Hindi switch | Respond in Hindi — agent matches (Devanagari) |
| Objection | Say "too expensive" / "महंगा है" |
| Barge-in | Interrupt while agent speaks |
| Escalation | Repeated anger or high-ticket intent |

## Extension Roadmap

- True streaming STT (partial transcripts)
- Streaming LLM tokens → early TTS start
- Celery/RQ swap for Redis queue (same job schema)
- Grafana dashboards on Prometheus metrics
- Human handoff SIP bridge on `escalate` state
