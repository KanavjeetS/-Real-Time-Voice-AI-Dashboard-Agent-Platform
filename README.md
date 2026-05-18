<div align="center">

# AI Calling Agent

### Real-time voice AI for outbound calls, CRM, and live analytics

[![Next.js](https://img.shields.io/badge/Next.js-14-000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Twilio](https://img.shields.io/badge/Twilio-Voice-F22F46?style=for-the-badge&logo=twilio&logoColor=white)](https://www.twilio.com/)
[![Groq](https://img.shields.io/badge/Groq-LLM%20%2B%20STT-f55036?style=for-the-badge)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-violet?style=for-the-badge)](LICENSE)

**[Live Dashboard](https://frontend-omega-six-37.vercel.app)** · **[API Docs](docs/ARCHITECTURE.md)** · **[Deploy Guide](docs/VERCEL_DEPLOY.md)**


---

## Overview

**AI Calling Agent** is a production-grade platform for AI-powered phone conversations: place outbound calls from a polished dashboard, stream audio through Twilio, transcribe with Whisper, reason with Llama, and respond with natural TTS — in **English and Hindi**.

Built for loan follow-up, sales, and support teams who need **low-latency**, **bilingual**, and **observable** voice automation.

| Capability | Detail |
|------------|--------|
| **Voice pipeline** | Twilio Media Streams → STT → LLM → TTS with barge-in |
| **Intelligence** | State machine, objections, intent scoring, escalation |
| **Enterprise** | Supabase CRM, call transcripts, Slack hot-lead alerts |
| **Scale** | Redis queue, background workers, Prometheus metrics |

---

## Architecture

```
┌─────────────┐     REST      ┌──────────────────┐
│  Dashboard  │ ────────────► │  FastAPI API     │
│  (Vercel)   │               │  (Railway)       │
└─────────────┘               └────────┬─────────┘
                                       │ WebSocket
┌─────────────┐     PSTN      ┌────────▼─────────┐
│   Phone     │ ◄───────────► │     Twilio       │
└─────────────┘               └──────────────────┘
```

**Layered design:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Quick start (local)

```bash
git clone https://github.com/KanavjeetS/-Real-Time-Voice-AI-Dashboard-Agent-Platform.git
cd -Real-Time-Voice-AI-Dashboard-Agent-Platform
cp .env.example .env   # add Groq + Twilio keys
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| Health | http://localhost:8000/health |

For phone testing, run `ngrok http 8000` and set `TWILIO_WEBHOOK_BASE_URL` in `.env`.

---

## Deploy (24/7)

| Component | Host |
|-----------|------|
| Dashboard | **Vercel** |
| Voice API | **Railway** or **Render** |
| Database | **Supabase** |
| Cache / queue | **Redis Cloud** |

Full walkthrough: **[docs/VERCEL_DEPLOY.md](docs/VERCEL_DEPLOY.md)**

---

## Environment

See [`.env.example`](.env.example). Required for calls:

- `GROQ_API_KEY`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- `TWILIO_WEBHOOK_BASE_URL` (public HTTPS API URL)

---

## Project structure

```
├── frontend/          # Next.js dashboard
├── backend/           # FastAPI + WebSocket voice handler
├── docs/              # Architecture, deployment, latency
├── scripts/           # DB init, dev helpers
├── Dockerfile         # API container (Railway/Render)
└── docker-compose.yml # Local full stack
```

---

## License

MIT — see [LICENSE](LICENSE).
