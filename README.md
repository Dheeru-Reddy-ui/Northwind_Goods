# Northwind Support AI

An **autonomous e-commerce customer support agent** for a fictional store,
"Northwind Goods" — the Sierra/Decagon product category. It doesn't just answer
questions; it **takes real actions** against a store backend (looks up orders,
checks eligibility, processes refunds, updates shipping), enforces business
rules, **escalates the hard tickets** to a human with a handoff summary, and
**traces + scores** every resolution. A one-click simulation replays a golden
test set so the ops dashboard is never empty.

> ### Runs with zero API keys
> Every external dependency (Postgres, Claude, Cohere, LangSmith) sits behind a
> swappable interface with a local fallback, so the whole product **boots and
> demos fully offline** on SQLite with a deterministic reasoning engine that
> runs the *same* tool-calling loop. Add an `ANTHROPIC_API_KEY` and it reasons
> with Claude instead — nothing else changes. This is a deliberate engineering
> choice: a reviewer can `git clone`, install, and have a working agent + chat +
> dashboard in two commands, then plug in real providers when they want.

---

## What it does (the 60-second tour)

1. **Customer chat** (`/`) — talk to the agent like a human rep: "where's my
   order," "I want a refund," "change my address," or an angry multi-part
   complaint. Its reasoning **streams live** (glass-box: "Checking refund
   eligibility → Processing your refund") and the answer streams token by token.
   Actions surface as chips; policy answers show source citations; escalations
   show a handoff card.
2. **Ops dashboard** (`/ops`) — live metric cards (resolution rate, escalation
   rate, judge score, cost, latency), a conversations table, a **pending-approvals**
   panel, and the signature **Agent Trace Timeline**: a vertical telemetry spine
   with color-coded, expandable nodes showing every model call, tool call,
   retrieval, guardrail, and escalation with per-step latency and cost.
3. **Run simulation** — replays 50 golden tickets through the agent live;
   conversations appear, metrics climb, escalations and approvals show up. "Reset
   demo" clears it.
4. **Impact & Insights** (`/ops/impact`, `/ops/insights`) — ROI numbers that
   recompute as you change the human-agent cost assumptions, and data-grounded
   recommendation cards generated only from the real aggregates (every figure is
   shown, none invented).

---

## Architecture

```
Customer ──chat/voice──▶ Next.js frontend ──▶ FastAPI /chat (+ /chat/stream SSE)
                                                     │
                                                     ▼
                                        LangGraph-style agent loop
                        ┌─────────────┬──────────────┴───────┬──────────────┐
                        ▼             ▼                      ▼              ▼
                  guardrails    knowledge base          store tools    escalation
                  (in / out)    (hybrid retrieval        (read/write     (handoff
                   PII redact     + RRF + rerank)          Postgres)      summary)
                        │             │                      │              │
                        └─────────────┴──────────┬───────────┴──────────────┘
                                                 ▼
                              trace + judge score  →  Postgres/SQLite
                                                 ▼
                        Ops dashboard: resolution rate, escalations,
                        judge scores, cost, and the Agent Trace Timeline
```

**Swappable everywhere:** LLM provider (`app/agent/llm.py`), database
(SQLAlchemy — SQLite or Postgres/Supabase via `DATABASE_URL`), retrieval
(local hashing embedding + BM25, or pgvector + Cohere rerank), tracing
(Postgres store, or LangSmith when a key is present).

## Tech stack

| Layer | Choice |
|------|--------|
| Backend / agent | Python 3.11+, FastAPI, LangGraph-style loop, Pydantic tool schemas |
| LLM | Anthropic Claude (swappable) · deterministic offline engine as fallback |
| Data / knowledge | SQLAlchemy (SQLite / Postgres·Supabase), hybrid retrieval (vector + BM25 + RRF), optional Cohere rerank |
| Eval / observability | golden set, LLM-as-judge, RAGAS-style metrics, per-step traces, LangSmith-optional |
| Frontend | Next.js (App Router) + TypeScript + Tailwind, Recharts |

## How the agent works

- **Tool-calling loop** (`app/agent/graph.py`) — a legible, fully-traced state
  machine: input guardrail → model → tools → model → … → output guardrail →
  finalize. Iteration-capped; per-session cost cap escalates instead of looping.
- **Tools** (`app/agent/tools.py`) — read (`lookup_customer/order`,
  `track_shipment`), retrieval (`search_knowledge_base`), write
  (`check_refund_eligibility`, `process_refund`, `update_shipping_address`,
  `cancel_order`), and `escalate_to_human`. Business rules live in the service
  layer, so the agent **physically cannot** process an out-of-policy refund.
- **Human-in-the-loop** — refunds over a threshold ($150) don't auto-execute;
  they park as a `PendingAction` and route to `/actions/{id}/approve|reject`.
- **Guardrails** (`app/agent/guardrails.py`) — input: block prompt-injection and
  cross-customer/internal exfiltration, redact PII from traces; output: block
  ungrounded refund claims and system-prompt leakage (→ escalate).
- **Escalation** — legal threats, chargebacks, high distress, out-of-scope
  requests write a handoff summary and give the customer an empathetic message.

## Evaluation — the "measure it" proof

`python -m eval.run` runs 50 golden tickets, scores each with an LLM-as-judge,
computes RAGAS-style retrieval metrics, and prints a category scorecard, storing
the run for regression comparison. The production agent scores **0.99 overall**
and beats a naive baseline by **+0.23 resolution** and **+0.18 policy adherence**.
A retrieval ablation (`python -m eval.retrieval`) shows hybrid retrieval trades a
marginal −0.05 recall for **+0.60 correct abstention** on off-topic queries.

See **[BENCHMARKS.md](BENCHMARKS.md)** for the full methodology, tables, and an
honest analysis of what did and didn't work.

```
  OVERALL              50      0.98    1.00    1.00   0.99     0.99   (resolve/policy/ground/tone/overall)
  Production vs naive:  resolution +0.23 · policy +0.18 · groundedness +0.16
```

## Quickstart

**Backend** (Windows paths shown; use `.venv/bin/...` on macOS/Linux):

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m app.store.seed          # seed the store
.venv/Scripts/python -m app.knowledge.ingest    # ingest policy docs
.venv/Scripts/python -m pytest                  # 16 tests
.venv/Scripts/uvicorn app.main:app --port 8000  # API on :8000
.venv/Scripts/python -m app.agent.cli           # or chat in the terminal
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev                                      # app on :3000
```

Open http://localhost:3000 (chat) and http://localhost:3000/ops (dashboard).
Click **Run simulation** to populate the dashboard.

**Docker (full stack):**

```bash
docker compose up --build      # backend :8000, frontend :3000
```

## Deployment

- **Backend** → a host that supports long-lived SSE (Fly.io / Render). The
  `Dockerfile` seeds + ingests on boot. Set `CORS_ORIGINS` to the frontend URL;
  optionally set `DATABASE_URL` (Supabase), `ANTHROPIC_API_KEY`, `COHERE_API_KEY`,
  `LANGSMITH_API_KEY`.
- **Frontend** → Vercel (or its `Dockerfile`). Set `NEXT_PUBLIC_API_BASE` to the
  backend URL.
- Secrets are read from env and never committed (`.env` is gitignored;
  `.env.example` documents every variable).

## Design decisions & trade-offs

- **Offline-first with swappable providers.** The single most important choice:
  the app must run and demo without six paid keys, but upgrade to real providers
  by setting env vars. Everything external is behind a thin interface.
- **Eligibility-first refunds + rule enforcement in the service layer.** The
  agent can try anything; the store rejects out-of-policy refunds. Safety doesn't
  depend on the model behaving.
- **Human-in-the-loop above a threshold.** High-value refunds are cheap to review
  and expensive to get wrong, so they never auto-execute.
- **Hybrid retrieval + honesty threshold over pure vector.** Not for recall (see
  BENCHMARKS — vector-only already nails recall here) but for **abstention**: the
  agent says "I don't have that" instead of inventing policy.
- **A hand-rolled, fully-traced loop instead of the LangGraph runtime.** Same
  node/edge model, but every step is visible and the loop stays dependency-light
  and trivially A/B-testable — which is what the trace timeline and eval harness
  are built on.

## Repo layout

```
backend/
  app/
    store/          e-commerce domain, policy rules, seed, REST endpoints
    agent/          llm provider, tools, deterministic engine, graph, guardrails, prompts
    knowledge/      policy docs ingestion + hybrid retriever
    observability/  tracing + metrics/trace API
    routers/        chat, chat_stream (SSE), actions (approvals), simulate
  eval/             golden tickets, judge, RAGAS, runner, retrieval ablation
  knowledge/        9 policy/FAQ markdown docs
  tests/            16 pytest tests
frontend/
  app/              chat (/) + ops dashboard (/ops)
  components/       chat, ops (trace timeline, metric cards, tables, approvals, simulation)
  lib/              typed API client, types, formatting
BENCHMARKS.md       evaluation report (methodology + honest analysis)
docker-compose.yml
```

## Build phases

Built and verified phase by phase — each layer works before the next is added:

| Phase | What | Status |
|------|------|--------|
| 0 | Store backend + seed + policy rules | ✅ |
| 1 | Agent core (tool-calling loop, read tools, `/chat`, CLI) | ✅ |
| 2 | Knowledge base (hybrid RAG for policies) | ✅ |
| 3 | Write actions, guardrails, escalation, human-in-the-loop | ✅ |
| 4 | Evaluation harness (golden set, judge, RAGAS, scorecard) | ✅ |
| 5 | Observability + tracing (per-step latency/cost, metrics API) | ✅ |
| 6 | Frontend (chat + ops dashboard + trace timeline + simulation) | ✅ |
| 7 | Live streaming agent reasoning (glass-box) | ✅ |
| 9 | Impact/ROI + insights analytics | ✅ |
| 10 | Docker + production hygiene (rate limit, cost cap) + docs | ✅ |
| 11 | Engineered depth — retrieval ablation ([BENCHMARKS.md](BENCHMARKS.md)) | ✅ |

Voice (Phase 8) is architected for but not built here — it needs live STT/TTS
keys and audio infrastructure.
