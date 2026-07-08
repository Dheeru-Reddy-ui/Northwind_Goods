# Northwind Support AI

An **autonomous e-commerce customer support agent** for a fictional store,
"Northwind Goods." It doesn't just answer questions — it takes real actions
against the store backend (looks up orders, checks eligibility, processes
refunds, updates shipping), enforces business rules, escalates the hard tickets
to a human with a handoff summary, and traces + scores every resolution.

> **Runs with zero API keys.** Every external dependency (Postgres, Claude,
> Cohere, LangSmith) sits behind a swappable interface with a local fallback,
> so the whole product boots and demos offline on SQLite with a deterministic
> reasoning engine. Add an `ANTHROPIC_API_KEY` and it reasons with Claude
> instead — nothing else changes.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy (SQLite locally / Postgres·Supabase in prod)
- **Agent:** LangGraph-style tool-calling loop, Anthropic Claude (swappable), Pydantic tool schemas
- **Knowledge base:** hybrid retrieval (vector + BM25) over policy docs, pgvector-swappable
- **Eval:** golden ticket set, LLM-as-judge, regression scorecard
- **Observability:** per-step traces (latency + token cost), metrics API
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind — chat + ops dashboard

## Quickstart (backend)

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

.venv/Scripts/python -m app.store.seed        # seed the store
.venv/Scripts/python -m app.knowledge.ingest  # ingest policy docs (Phase 2+)
.venv/Scripts/python -m pytest                # tests
.venv/Scripts/uvicorn app.main:app --reload   # run API on :8000

.venv/Scripts/python -m app.agent.cli         # chat in the terminal
```

Open http://localhost:8000/docs for the API, http://localhost:8000/health for a health check.

## Build phases

Built and verified phase by phase — each layer works before the next is added:

| Phase | What | Status |
|------|------|--------|
| 0 | Store backend + seed + policy rules | ✅ |
| 1 | Agent core (tool-calling loop, read tools, `/chat`, CLI) | ✅ |
| 2 | Knowledge base (RAG for policies) | in progress |
| 3 | Write actions, guardrails, escalation, human-in-the-loop | — |
| 4 | Evaluation harness (golden set, judge, scorecard) | — |
| 5 | Observability + tracing | — |
| 6 | Frontend (chat + ops dashboard + simulation) | — |
| 7 | Live streaming agent reasoning | — |

See `backend/` for the API and agent, `frontend/` for the web app.
