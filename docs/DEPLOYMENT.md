# Deployment Guide

Operational guide for running **AI Calling Agent** locally and in production.

> **System design:** See [ARCHITECTURE.md](./ARCHITECTURE.md) for deployment topology, component responsibilities, and webhook configuration.

## Quick start (Docker — recommended)

```bash
cp .env.example .env
# Set: POSTGRES_PASSWORD, REDIS_PASSWORD, GROQ_API_KEY, Twilio vars

docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| Metrics | http://localhost:8000/metrics |
| API docs | http://localhost:8000/docs |

### Services

- `postgres` — CRM schema via `scripts/init_db.sql`
- `redis` — session memory + job queue
- `api` — FastAPI voice + REST
- `worker` — background jobs (summaries, Slack, scoring)
- `frontend` — Next.js dashboard

### Scale workers

```bash
docker compose up --scale worker=3 -d
```

## Local development

```bash
# API
python -m uvicorn main:app --app-dir backend --port 8000

# Worker (separate terminal)
cd backend && python run_worker.py

# Frontend
cd frontend && npm run dev -- -p 3001
```

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROQ_API_KEY` | Yes | STT + LLM |
| `TWILIO_*` | For calls | Telephony |
| `TWILIO_WEBHOOK_BASE_URL` | Yes | ngrok HTTPS URL |
| `DATABASE_URL` | CRM | `postgresql+asyncpg://...` |
| `REDIS_URL` | Queue/memory | `redis://:password@host:6379/0` |
| `SLACK_WEBHOOK_URL` | Optional | Hot-lead alerts |

## ngrok (phone testing)

```bash
ngrok http 8000
# Set TWILIO_WEBHOOK_BASE_URL=https://xxxx.ngrok-free.app
```

## Production checklist

- [ ] `APP_ENV=production`
- [ ] Strong Postgres + Redis passwords
- [ ] Run at least 2 API workers behind load balancer (sticky WS)
- [ ] Run 2+ `worker` replicas
- [ ] Prometheus scrape `/metrics`
- [ ] `STARTUP_WARM_MODELS=true` for stable first-call latency

## Failover

- Groq LLM: 3 retries with exponential backoff on 429
- STT: empty transcript on failure (skip turn, no crash)
- Redis down: in-memory memory fallback + sync CRM where possible
- DB down: default agent + no persistence (degraded mode)
