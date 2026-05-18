# Deploy AI Calling Agent (24/7)

The stack splits across two hosts — **Vercel cannot run voice WebSockets or Kokoro TTS**.

| Component | Host | Why |
|-----------|------|-----|
| **Dashboard** (Next.js) | **Vercel** | Static/SSR UI, global CDN |
| **Voice API** (FastAPI + Twilio WS) | **Railway** or **Render** | Long-lived WebSockets, Python, TTS models |
| **Database** | Supabase | Already configured |
| **Redis** | Redis Cloud | Queue + session memory |

## 1. Push to GitHub

```bash
cd vahanai
git init
git add .
git commit -m "AI Calling Agent — production deploy setup"
git branch -M main
git remote add origin https://github.com/KanavjeetS/-Real-Time-Voice-AI-Dashboard-Agent-Platform.git
git push -u origin main
```

## 2. Deploy API (Railway — recommended)

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo.
2. Select this repository; Railway detects `Dockerfile` via `railway.toml`.
3. Set **environment variables** (from `.env.example`, never commit real `.env`):

   | Variable | Example |
   |----------|---------|
   | `GROQ_API_KEY` | your Groq key |
   | `TWILIO_ACCOUNT_SID` | AC... |
   | `TWILIO_AUTH_TOKEN` | ... |
   | `TWILIO_PHONE_NUMBER` | +1... |
   | `TWILIO_WEBHOOK_BASE_URL` | `https://<railway-app>.up.railway.app` |
   | `DATABASE_URL` | `postgresql+asyncpg://...` (Supabase) |
   | `REDIS_URL` | Redis Cloud URL |
   | `USE_DATABASE` | `true` |
   | `CORS_ORIGINS` | `["https://your-app.vercel.app"]` |
   | `APP_ENV` | `production` |
   | `STARTUP_WARM_MODELS` | `true` |

4. Generate a **public domain** in Railway → copy URL.
5. Set `TWILIO_WEBHOOK_BASE_URL` to that URL (no trailing slash).
6. In Twilio Console, no change needed if webhooks use the URL from your app on call initiate.

## 3. Deploy dashboard (Vercel)

1. Go to [vercel.com](https://vercel.com) → Add New Project → Import GitHub repo.
2. **Root Directory**: set to `frontend` (important).
3. Environment variable:

   ```
   NEXT_PUBLIC_API_URL=https://<your-railway-api>.up.railway.app
   ```

4. Deploy. Open `https://<project>.vercel.app`.

## 4. Verify

- `https://<api>/health` → `status: ok`, Twilio + Groq configured.
- Dashboard shows **Online** (green).
- Place a test call from the **Dial** tab.

## GitHub Actions (optional)

Add repo secrets: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` — then pushes to `main` auto-deploy the frontend.

## Local vs production

| | Local | Production |
|---|--------|------------|
| Dashboard | `npm run dev` in `frontend/` | Vercel URL |
| API | `uvicorn` + ngrok | Railway URL |
| Twilio webhooks | ngrok | Railway public URL |
