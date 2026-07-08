"""Ingestion pipeline: markdown policy docs -> chunks -> embeddings -> DB.

Structure-aware chunking by heading (each ## section becomes one chunk, with
the document title prepended for context). Idempotent: re-running clears and
re-ingests, so it never duplicates. Run separately from the query path:

    python -m app.knowledge.ingest
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete

from app.db.database import SessionLocal, init_db
from app.db.models import KnowledgeChunk
from app.knowledge.text import embed, tokenize

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"


def chunk_markdown(text: str, source: str) -> list[dict]:
    """Split into (title, section, body) chunks by ## headings."""
    title = source.replace(".md", "").replace("_", " ").title()
    chunks: list[dict] = []
    section = "Overview"
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            content = f"{title} — {section}\n{body}"
            chunks.append({"section": section, "content": content})

    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            section = line[3:].strip()
            buffer = []
        else:
            buffer.append(line)
    flush()
    return chunks


def ingest() -> dict:
    init_db()
    db = SessionLocal()
    try:
        db.execute(delete(KnowledgeChunk))
        db.commit()
        files = sorted(KNOWLEDGE_DIR.glob("*.md"))
        total = 0
        for path in files:
            text = path.read_text(encoding="utf-8")
            for chunk in chunk_markdown(text, path.name):
                tokens = tokenize(chunk["content"])
                db.add(KnowledgeChunk(
                    source=path.name, section=chunk["section"], content=chunk["content"],
                    embedding=embed(tokens), token_count=len(tokens),
                ))
                total += 1
        db.commit()
        return {"files": len(files), "chunks": total}
    finally:
        db.close()


def main() -> None:
    result = ingest()
    print(f"Ingested {result['chunks']} chunks from {result['files']} policy documents.")


if __name__ == "__main__":
    main()
