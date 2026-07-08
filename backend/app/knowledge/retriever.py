"""Hybrid retrieval: vector + BM25 fused with RRF, then optional Cohere rerank.

Two first-stage retrievers (a hashing embedding for soft term overlap and BM25
for keyword precision) are combined with Reciprocal Rank Fusion, then the top
candidates are optionally reranked with Cohere (production-standard second
stage). If COHERE_API_KEY is absent we log once and use the fused order.

An honesty threshold means an off-topic query returns no passages, so the agent
says "I don't have that" instead of grounding an answer in an irrelevant doc.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import KnowledgeChunk
from app.knowledge.text import BM25, cosine, embed, tokenize

logger = logging.getLogger("northwind.retriever")

RRF_K = 60
# Keyword overlap (BM25) is the honest relevance signal: it's ~0 when the query
# shares no terms with any doc. The hashed embedding's cosine has spurious
# collision noise, so it informs ranking but not the include/exclude gate.
MIN_BM25 = 0.5
MIN_COSINE = 0.40
_cohere_warned = False


def _rrf(rankings: list[list[int]]) -> dict[int, float]:
    """Reciprocal Rank Fusion over several ranked lists of doc indices."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


def _maybe_rerank(query: str, candidates: list[dict]) -> list[dict]:
    global _cohere_warned
    if not settings.cohere_api_key:
        if not _cohere_warned:
            logger.warning("COHERE_API_KEY not set — using fused ranking without rerank.")
            _cohere_warned = True
        return candidates
    try:
        import cohere

        co = cohere.Client(settings.cohere_api_key)
        docs = [c["content"] for c in candidates]
        res = co.rerank(model="rerank-english-v3.0", query=query, documents=docs, top_n=len(docs))
        order = [r.index for r in res.results]
        return [candidates[i] for i in order]
    except Exception as e:  # any failure -> graceful fallback to fused order
        logger.warning("Cohere rerank failed (%s); using fused ranking.", e)
        return candidates


def search(db: Session, query: str, top_k: int = 3) -> list[dict]:
    chunks = list(db.scalars(select(KnowledgeChunk)).all())
    if not chunks:
        return []

    qtokens = tokenize(query)
    qvec = embed(qtokens)

    corpus = [tokenize(c.content) for c in chunks]
    bm25 = BM25(corpus)
    bm25_scores = bm25.scores(qtokens)
    vec_scores = [cosine(qvec, c.embedding or []) for c in chunks]

    vec_rank = sorted(range(len(chunks)), key=lambda i: vec_scores[i], reverse=True)
    bm25_rank = sorted(range(len(chunks)), key=lambda i: bm25_scores[i], reverse=True)
    fused = _rrf([vec_rank, bm25_rank])

    # Keep only chunks with real relevance signal (honesty threshold).
    candidates = [
        i for i in fused
        if bm25_scores[i] > MIN_BM25 or vec_scores[i] >= MIN_COSINE
    ]
    if not candidates:
        return []
    candidates.sort(key=lambda i: fused[i], reverse=True)

    top = candidates[:10]
    passages = [{
        "source": chunks[i].source,
        "section": chunks[i].section,
        "content": chunks[i].content,
        "snippet": _snippet(chunks[i].content),
        "vector_score": round(vec_scores[i], 4),
        "bm25_score": round(bm25_scores[i], 4),
        "fused_score": round(fused[i], 4),
    } for i in top]

    passages = _maybe_rerank(query, passages)
    return passages[:top_k]


def _snippet(content: str, max_chars: int = 600) -> str:
    """Drop the 'Title — Section' prefix line; return the body, trimmed."""
    body = content.split("\n", 1)[1] if "\n" in content else content
    body = body.strip()
    return body if len(body) <= max_chars else body[:max_chars].rsplit(" ", 1)[0] + "…"
