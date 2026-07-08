"""Retrieval-quality ablation (Phase 11, Track B).

Measures *why* hybrid + fusion beats naive vector search, and by how much, on a
labeled query -> ground-truth-source set. Reports recall@1/3/5 and MRR for two
configurable pipelines:

    (1) vector-only  — cosine over the hashing embedding (the naive baseline)
    (2) hybrid+RRF   — vector + BM25 fused with Reciprocal Rank Fusion

    python -m eval.retrieval        # prints the table, writes BENCHMARKS section
"""
from __future__ import annotations

import statistics
from pathlib import Path

from app.db.database import SessionLocal, init_db
from app.knowledge.ingest import ingest
from app.knowledge.retriever import search, search_vector_only

# query -> the doc that should be retrieved
LABELED: list[tuple[str, str]] = [
    ("what is your return policy", "return_policy.md"),
    ("how many days do I have to return an item", "return_policy.md"),
    ("can I return a final sale item", "return_policy.md"),
    ("how long does a refund take to arrive", "faq.md"),
    ("how are refunds issued", "refund_process.md"),
    ("do high value refunds need approval", "refund_process.md"),
    ("how much does shipping cost", "shipping_policy.md"),
    ("what is the free shipping threshold", "shipping_policy.md"),
    ("how fast is express shipping", "shipping_policy.md"),
    ("can I cancel my order", "order_cancellation.md"),
    ("cancel an order before it ships", "order_cancellation.md"),
    ("my item arrived broken", "damaged_items.md"),
    ("what do I do about a damaged package", "damaged_items.md"),
    ("is there a warranty on electronics", "warranty.md"),
    ("how long is the warranty", "warranty.md"),
    ("what are your support hours", "contact_hours.md"),
    ("when are you open", "contact_hours.md"),
    ("do you ship internationally", "international_shipping.md"),
    ("which countries do you ship to", "international_shipping.md"),
]

# Off-topic queries: the correct answer is to retrieve NOTHING (abstain) so the
# agent says "I don't have that" instead of grounding an answer in a stray chunk.
OFF_TOPIC: list[str] = [
    "what is the weather on mars",
    "do you sell live goldfish",
    "who is the ceo's spouse",
    "recommend a good pizza recipe",
    "what is the stock price today",
]


def _rank_of(passages: list[dict], source: str) -> int | None:
    for i, p in enumerate(passages):
        if p["source"] == source:
            return i + 1
    return None


def _metrics(pipeline) -> dict:
    db = SessionLocal()
    ranks: list[int | None] = []
    try:
        for query, gold in LABELED:
            passages = pipeline(db, query, 5)
            ranks.append(_rank_of(passages, gold))
    finally:
        db.close()
    n = len(ranks)
    recall_at = lambda k: sum(1 for r in ranks if r is not None and r <= k) / n
    mrr = statistics.mean(1 / r if r else 0 for r in ranks)
    return {
        "recall@1": round(recall_at(1), 3),
        "recall@3": round(recall_at(3), 3),
        "recall@5": round(recall_at(5), 3),
        "mrr": round(mrr, 3),
    }


def _abstention(pipeline) -> float:
    """Fraction of off-topic queries the pipeline correctly returns empty for."""
    db = SessionLocal()
    try:
        correct = sum(1 for q in OFF_TOPIC if len(pipeline(db, q, 5)) == 0)
    finally:
        db.close()
    return round(correct / len(OFF_TOPIC), 3)


def run() -> dict:
    init_db()
    ingest()
    vo = _metrics(search_vector_only)
    hy = _metrics(search)
    vo["abstention"] = _abstention(search_vector_only)
    hy["abstention"] = _abstention(search)
    return {"vector_only": vo, "hybrid_rrf": hy, "n": len(LABELED), "n_off": len(OFF_TOPIC)}


def format_report(res: dict) -> str:
    v, h = res["vector_only"], res["hybrid_rrf"]
    lines = [
        f"Retrieval ablation ({res['n']} labeled queries, {res['n_off']} off-topic)",
        f"  {'config':<16}{'recall@1':>10}{'recall@3':>10}{'recall@5':>10}{'MRR':>8}{'abstain':>9}",
        f"  {'-' * 61}",
        f"  {'vector-only':<16}{v['recall@1']:>10.2f}{v['recall@3']:>10.2f}{v['recall@5']:>10.2f}{v['mrr']:>8.2f}{v['abstention']:>9.2f}",
        f"  {'hybrid+RRF':<16}{h['recall@1']:>10.2f}{h['recall@3']:>10.2f}{h['recall@5']:>10.2f}{h['mrr']:>8.2f}{h['abstention']:>9.2f}",
        f"  {'Δ (hybrid−vec)':<16}{h['recall@1']-v['recall@1']:>+10.2f}{h['recall@3']-v['recall@3']:>+10.2f}"
        f"{h['recall@5']-v['recall@5']:>+10.2f}{h['mrr']-v['mrr']:>+8.2f}{h['abstention']-v['abstention']:>+9.2f}",
    ]
    return "\n".join(lines)


def _store(res: dict) -> None:
    from app.db.database import SessionLocal
    from app.db.models import EvalRun

    db = SessionLocal()
    try:
        db.add(EvalRun(mode="retrieval", total=res["n"], metrics=res))
        db.commit()
    finally:
        db.close()


def main() -> None:
    res = run()
    _store(res)
    print("\n" + format_report(res) + "\n")


if __name__ == "__main__":
    main()
