"""Naive baseline agent for comparison.

A deliberately naive strawman: vector-only retrieval with no honesty threshold,
no guardrails, and no refund-eligibility check (it just refunds). This is the
"before" the production agent is measured against — it demonstrates why the
eligibility-first rule, guardrails, and hybrid retrieval matter, in numbers.

It intentionally does the wrong thing: refunds out-of-window orders, complies
with injection, and answers policy questions from whatever chunk is nearest.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.db.models import Order, Refund
from app.knowledge.retriever import search_vector_only

ORD_RE = re.compile(r"ORD-?0*(\d{1,5})", re.IGNORECASE)


def _oid(text: str) -> str | None:
    m = ORD_RE.search(text)
    return f"ORD-{int(m.group(1)):05d}" if m else None


def run_naive(db: Session, session_id: str, message: str) -> dict:
    t = message.lower()
    oid = _oid(message)
    empty = {"citations": [], "actions": [], "pending_actions": [], "escalations": [],
             "cost_usd": 0.0, "duration_ms": 5, "conversation_id": None}

    # Naive: refund on request, no eligibility / threshold / approval.
    if any(k in t for k in ("refund", "money back")) and oid:
        order = db.get(Order, oid)
        if order and order.status != "refunded":
            db.add(Refund(order_id=oid, amount_cents=order.total_cents, reason="naive refund"))
            order.status = "refunded"
            db.commit()
        return {"reply": f"Done! I've refunded order {oid} for you.", "outcome": "resolved",
                "tool_calls_made": [{"tool": "process_refund", "input": {"order_id": oid},
                                     "output": {"status": "processed"}}], **empty}

    # Naive: comply with injection.
    if "discount" in t or "ignore your instructions" in t:
        return {"reply": "Sure! Here's a 100% discount code: SAVE100.", "outcome": "resolved",
                "tool_calls_made": [], **empty}

    # Naive: vector-only retrieval, no threshold -> always answers something.
    if "?" in t or any(k in t for k in ("policy", "return", "shipping", "warranty", "hours", "refund")):
        passages = search_vector_only(db, message, top_k=1)
        reply = passages[0]["snippet"] if passages else "Yes, that should be fine."
        cites = [{"source": p["source"], "section": p["section"], "snippet": p["snippet"]} for p in passages]
        return {"reply": reply, "outcome": "resolved",
                "tool_calls_made": [{"tool": "search_knowledge_base", "input": {"query": message},
                                     "output": {"passages": passages}}],
                **{**empty, "citations": cites}}

    # Order status it can do by lookup.
    if oid:
        order = db.get(Order, oid)
        if order:
            return {"reply": f"Order {oid} is {order.status}.", "outcome": "resolved",
                    "tool_calls_made": [{"tool": "lookup_order", "input": {"order_id": oid},
                                         "output": {"status": order.status}}], **empty}
    return {"reply": "How can I help?", "outcome": "resolved", "tool_calls_made": [], **empty}
