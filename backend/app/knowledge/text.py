"""Local text primitives: tokenizer, a hashing embedding, and BM25.

These give the knowledge base real hybrid retrieval with zero external
services. The embedding is a hashed bag-of-words (unigrams + bigrams, light
stemming) — lexical, not semantic, but paired with BM25 and fused with RRF it
retrieves the right policy doc reliably for this corpus. Swap `embed` for a
real embedding model and the `embedding` column for pgvector in production;
the retriever interface doesn't change.
"""
from __future__ import annotations

import math
import re
import zlib
from collections import Counter

EMBED_DIM = 768

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "be",
    "with", "you", "your", "i", "it", "this", "that", "we", "our", "can", "do", "does",
    "how", "what", "when", "at", "as", "by", "if", "my", "me", "so", "from", "will",
}


def _stem(word: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


def _h(token: str) -> int:
    return zlib.crc32(token.encode("utf-8")) % EMBED_DIM


def embed(tokens: list[str]) -> list[float]:
    """Hashed bag-of-words (unigrams + bigrams), L2-normalized."""
    vec = [0.0] * EMBED_DIM
    for t in tokens:
        vec[_h(t)] += 1.0
    for a, b in zip(tokens, tokens[1:]):
        vec[_h(f"{a}_{b}")] += 0.5
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both are L2-normalized


class BM25:
    """Standard BM25 over a token corpus."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.corpus = corpus
        self.k1, self.b = k1, b
        self.N = len(corpus)
        self.doc_len = [len(d) for d in corpus]
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        self.tf = [Counter(d) for d in corpus]
        df: Counter = Counter()
        for d in corpus:
            for term in set(d):
                df[term] += 1
        self.idf = {
            term: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for term, n in df.items()
        }

    def scores(self, query: list[str]) -> list[float]:
        out = [0.0] * self.N
        for i in range(self.N):
            score = 0.0
            for term in query:
                if term not in self.tf[i]:
                    continue
                freq = self.tf[i][term]
                idf = self.idf.get(term, 0.0)
                denom = freq + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1))
                score += idf * (freq * (self.k1 + 1)) / (denom or 1)
            out[i] = score
        return out
