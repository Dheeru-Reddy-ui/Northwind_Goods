"""RAGAS-style retrieval metrics for policy answers.

Lightweight, offline proxies for the three RAGAS metrics (swap in the RAGAS
library with an LLM for the full versions; the interface is the same):

- faithfulness      : fraction of the answer's content tokens supported by the
                      retrieved context (grounded vs. invented).
- answer_relevance  : overlap between the answer and the question.
- context_precision : fraction of retrieved passages from the correct source
                      (when a gold source is known), else whether any relevant
                      passage was retrieved.
"""
from __future__ import annotations

from app.knowledge.text import tokenize


def _get_passages(result: dict) -> list[dict]:
    for tc in result.get("tool_calls_made", []):
        if tc["tool"] == "search_knowledge_base":
            return (tc.get("output") or {}).get("passages", []) or []
    return []


def rag_metrics(question: str, result: dict, expected_source: str | None = None) -> dict:
    answer = result.get("reply", "")
    passages = _get_passages(result)

    ans = set(tokenize(answer))
    q = set(tokenize(question))
    ctx = set()
    for p in passages:
        ctx |= set(tokenize(p.get("content", "")))

    faithfulness = (len(ans & ctx) / len(ans)) if ans else 0.0
    answer_relevance = (len(ans & q) / len(q)) if q else 0.0
    if expected_source and passages:
        context_precision = sum(1 for p in passages if p.get("source") == expected_source) / len(passages)
    elif passages:
        context_precision = 1.0
    else:
        context_precision = 0.0

    return {
        "faithfulness": round(faithfulness, 3),
        "answer_relevance": round(answer_relevance, 3),
        "context_precision": round(context_precision, 3),
    }
