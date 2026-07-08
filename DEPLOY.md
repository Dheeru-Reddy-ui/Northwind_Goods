# Deploying Northwind Support AI

Two moving parts: the **FastAPI backend** (needs a host that supports long-lived
SSE + WebSocket for streaming reasoning and voice) and the **Next.js frontend**.
Both run with zero API keys; add provider keys as env vars only if you want them.

Config files included: `backend/fly.toml`, `render.yaml`, `backend/Dockerfile`,
`frontend/Dockerfile`, `docker-compose.yml`.

---

## Option A — Fly.io (backend) + Vercel (frontend)  ·  recommended

### 1. Backend → Fly.io
```bash
# one-time: install flyctl + log in
#   Windows:  pwsh -c "iwr https://fly.io/install.ps1 -useb | iex"
#   macOS/Linux:  curl -L https://fly.io/install.sh | sh
fly auth login

cd backend
fly launch --copy-config --no-deploy      # uses fly.toml; pick an app name/region
# set your frontend origin for CORS (update after you know the Vercel URL):
fly secrets set CORS_ORIGINS="https://<your-frontend>.vercel.app"
# optional real providers:
# fly secrets set ANTHROPIC_API_KEY=sk-ant-...  DATABASE_URL=postgresql+psycopg2://...
fly deploy
```
Fly gives you `https://<app>.fly.dev`. Check `https://<app>.fly.dev/health`.

### 2. Frontend → Vercel
```bash
npm i -g vercel
cd frontend
vercel                                     # link/create the project
vercel env add NEXT_PUBLIC_API_BASE        # value: https://<app>.fly.dev
vercel --prod
```

### 3. Close the loop
Set the backend's `CORS_ORIGINS` to the Vercel production URL and redeploy the
backend (`fly deploy`). Done — visit the Vercel URL.

---

## Option B — Render (both services, one blueprint)
1. Push this repo to GitHub.
2. Render dashboard → **New > Blueprint** → select the repo (`render.yaml` is auto-detected).
3. It provisions `northwind-backend` (Docker) and `northwind-frontend` (Node).
4. After first deploy, confirm the two URLs match the `envVars` in `render.yaml`
   (`CORS_ORIGINS` on the backend, `NEXT_PUBLIC_API_BASE` on the frontend); edit
   if Render assigned different names, then redeploy.

Note: Render's free tier spins services down when idle — the first request after
idle cold-starts (a few seconds), which can drop an in-flight SSE/voice socket;
retry once. For an always-warm demo use a paid instance or Fly with
`min_machines_running = 1`.

---

## Local, containerized (parity check before deploying)
```bash
docker compose up --build      # backend :8000, frontend :3000
```

## Environment variables (all optional)
| Var | Where | Purpose |
|-----|-------|---------|
| `CORS_ORIGINS` | backend | allowed frontend origin(s) |
| `NEXT_PUBLIC_API_BASE` | frontend | backend URL |
| `ANTHROPIC_API_KEY` | backend | use Claude instead of the offline engine |
| `DATABASE_URL` | backend | Postgres/Supabase instead of SQLite |
| `COHERE_API_KEY` | backend | second-stage rerank |
| `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` | backend | server-side voice STT/TTS |
| `LANGSMITH_API_KEY` | backend | LangSmith tracing |

Secrets are read from env and never committed (`.env` is gitignored;
`backend/.env.example` documents everything).
