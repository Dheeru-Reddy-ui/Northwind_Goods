# Benchmarks & Evaluation Report

Every number here is reproducible from the repo with no API keys (the offline
deterministic engine is used unless `ANTHROPIC_API_KEY` is set). Methodology is
stated so the results are legible and defensible, **including what didn't work.**

```bash
cd backend
.venv/Scripts/python -m eval.run          # resolution scorecard (production vs naive)
.venv/Scripts/python -m eval.retrieval    # retrieval ablation
```

---

## 1. Resolution quality — production agent vs. naive baseline

**Method.** 50 golden tickets across 12 categories (`eval/golden_tickets.yaml`),
each with an expected outcome and checks. The store is re-seeded before every
ticket so refund/cancel tickets are deterministic. Each resolution is scored by
an LLM-as-judge (`eval/judge.py`) on four dimensions with a strict, category-aware
rubric — harsh on the failures that matter (refunding outside policy, auto-executing
a high-value refund, following an injected instruction, asserting facts with no
tool call). The **naive baseline** (`eval/baseline.py`) is a deliberate strawman:
vector-only retrieval with no honesty threshold, no guardrails, and no
eligibility check (it just refunds).

**Result.**

| Metric (overall)     | Production | Naive | Δ      |
|----------------------|-----------:|------:|-------:|
| Resolution success   | **0.98**   | 0.75  | +0.23  |
| Policy adherence     | **1.00**   | 0.82  | +0.18  |
| Groundedness         | **1.00**   | 0.84  | +0.16  |
| Overall              | **0.99**   | 0.84  | +0.16  |

Per-category (production): order_status, policy_qa, refund_eligible,
refund_ineligible, refund_approval, cancellation, injection, exfiltration all
score 1.00; address_change 1.00; escalation 0.96; policy_unknown 0.95.

**Where the gap comes from.** The naive agent loses almost all of its points on
exactly the cases that define an autonomous support agent: it refunds
out-of-window orders (policy_adherence), auto-executes the $318 refund that
should need approval, complies with the injection ("here's a 100% discount"),
and answers off-topic questions from the nearest chunk (groundedness). The
production agent's eligibility-first rule, approval gate, and guardrails are what
close the gap — and the scorecard puts a number on each.

## 2. RAGAS-style retrieval metrics (policy answers)

Offline proxies for the three RAGAS metrics over the `policy_qa` tickets:

| faithfulness | answer_relevance | context_precision |
|-------------:|-----------------:|------------------:|
| 0.67         | 0.79             | 0.80              |

(Faithfulness = answer content supported by retrieved context; relevance =
answer↔question overlap; precision = retrieved passages from the correct source.)

---

## 3. Retrieval ablation — *why* hybrid, and where it doesn't help

**Method.** 19 labeled `query → ground-truth-doc` pairs plus 5 deliberately
off-topic queries whose correct behavior is to **retrieve nothing**. Two
pipelines: naive vector-only (cosine over the hashing embedding) vs. hybrid
(vector + BM25 fused with Reciprocal Rank Fusion, plus the honesty threshold).

**Result.**

| config          | recall@1 | recall@3 | recall@5 | MRR  | abstain |
|-----------------|---------:|---------:|---------:|-----:|--------:|
| vector-only     | 0.84     | **1.00** | **1.00** | 0.92 | 0.00    |
| hybrid + RRF    | 0.84     | 0.95     | 0.95     | 0.90 | **0.60**|
| Δ (hybrid−vec)  | +0.00    | −0.05    | −0.05    | −0.03| **+0.60** |

**Honest analysis (this is the interesting part).** On this small, clean policy
corpus, vector-only retrieval is *already* excellent — recall@3 = 1.00 — and
adding BM25 fusion **did not improve recall; it slightly hurt it** (−0.05 at
k=3), because RRF occasionally demotes the one right doc when a common term
(e.g. "number", "price") ranks another chunk highly. If recall were the only
metric, the ablation would say "hybrid wasn't worth it here."

But recall isn't the metric that matters for a support agent. **Vector-only
never abstains** (0.00) — it returns its nearest chunk for *every* query,
including "what's the weather on Mars," so a naive agent would confidently
ground a policy answer in an irrelevant document. The hybrid pipeline's
BM25-driven honesty threshold correctly abstains on 60% of off-topic queries
(+0.60). **The right trade for this product is a marginal recall cost for large
abstention gains** — a wrong-but-confident policy answer costs far more than the
right doc landing at rank 4 instead of 3. That trade is the reason the
production agent scores 1.00 on groundedness while the naive one scores 0.84.

---

## 4. Reliability benchmark (Track A — τ-bench style)

**Method.** Each golden task is run N times (`eval/reliability.py`). We report
success rate and **consistency = pass^k** (the fraction of tasks that succeed in
*all* k runs) plus a k-run success histogram and a failure-mode taxonomy
(`wrong_tool`, `bad_tool_args`, `loop_or_timeout`, `gave_up`, `policy_violation`,
`wrong_answer`) auto-classified from the trace. It A/Bs a reliability
safeguard (`reliability_fixes`): tool-layer enforcement that eligibility is
verified *before* any irreversible refund executes — not merely requested in the
prompt (a refund tool call without a prior `check_refund_eligibility` this turn
returns `needs_verification` and forces the check).

**Offline baseline (deterministic engine, N=5, 50 tasks):**

| config      | success_rate | pass^k (consistency) |
|-------------|-------------:|---------------------:|
| fixes OFF   | 0.98         | 0.98                 |
| fixes ON    | 0.98         | 0.98                 |

k-run distribution: `{5: 49, 0: 1}` — every task either passes all 5 runs or
none. That all-or-nothing shape is the point: the deterministic engine has **zero
run-to-run variance**, so consistency equals success and the safeguard shows no
delta (it always verified first anyway). This is the honest control.

**Where it gets interesting.** Non-determinism — and therefore the gap between
success rate and consistency, and the payoff from the safeguard — only appears
on the Claude path. Set `ANTHROPIC_API_KEY` in `backend/.env` and run:

```bash
.venv/Scripts/python -m eval.reliability --n 10   # LLM-path pass^k + failure taxonomy
.venv/Scripts/python -m eval.run                  # LLM-path resolution scorecard
```

The harness prints the provider it's measuring and A/Bs the safeguard, so the
before/after (success + consistency + failure modes) drops out directly.

---

## Reproducing

```bash
cd backend
.venv/Scripts/python -m eval.run --mode both     # section 1 + 2
.venv/Scripts/python -m eval.run --baseline      # diff vs the previous stored run
.venv/Scripts/python -m eval.retrieval           # section 3
```
Runs are written to the `eval_runs` table so they're comparable over time.
