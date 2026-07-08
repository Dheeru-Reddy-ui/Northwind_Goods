"""Robustness tests: human/conversational inputs must be safe and sensible.

Guards against the failure modes found during hardening: false escalation on
identity questions, policy-snippet leakage on off-topic input, "None" leaks when
an action is requested without an order id, and refunding the wrong order in a
multi-order message.
"""
from __future__ import annotations

import uuid

import pytest

from app.agent.graph import run_agent
from app.db.models import Order
from app.knowledge.ingest import ingest_into
from app.store.seed import seed


@pytest.fixture()
def seeded(db):
    seed(db)
    ingest_into(db)  # populate the KB so retrieval tests are meaningful
    return db


def ask(db, msg: str) -> dict:
    return run_agent(db, f"c-{uuid.uuid4().hex[:6]}", msg)


@pytest.mark.parametrize("msg", [
    "hi", "hello there!", "thanks so much!", "goodbye", "ok", "yes", "asdfghjkl",
    "😀🎉", "...", "   ", "how are you?", "tell me a joke", "you're amazing",
    "you're useless", "what is 2+2?", "i'm really frustrated", "i have a problem",
])
def test_no_errors_and_non_empty(seeded, msg):
    r = ask(seeded, msg)
    assert r["reply"].strip(), f"empty reply for {msg!r}"
    assert r["outcome"] in ("resolved", "escalated", "pending_approval")


def test_identity_is_not_escalated(seeded):
    for q in ("who are you?", "are you a real person?", "are you a bot?", "what are you?"):
        r = ask(seeded, q)
        assert r["outcome"] == "resolved"
        assert r["tool_calls_made"] == []
        assert any(w in r["reply"].lower() for w in ("assistant", "ai", "virtual"))


def test_offtopic_does_not_leak_policy(seeded):
    for q in ("what's the capital of France?", "who won the world cup?", "do you like music?"):
        r = ask(seeded, q)
        assert not r["citations"], f"leaked policy for {q!r}"


def test_action_without_id_asks_and_does_not_call_tool(seeded):
    for q in ("i want to cancel my order", "change my address", "can I get a refund?"):
        r = ask(seeded, q)
        assert r["tool_calls_made"] == [], f"tool called without id for {q!r}"
        assert "None" not in r["reply"]
        assert "order number" in r["reply"].lower()


def test_multi_order_refunds_the_right_one(seeded):
    r = ask(seeded, "where is ORD-00012 and can I refund ORD-00007?")
    # ORD-00007 is refunded; ORD-00012 (the one asked about for status) is not.
    assert seeded.get(Order, "ORD-00007").status == "refunded"
    assert seeded.get(Order, "ORD-00012").status != "refunded"


def test_support_hours_uses_knowledge_base(seeded):
    r = ask(seeded, "What are your support hours?")
    assert any(t["tool"] == "search_knowledge_base" for t in r["tool_calls_made"])
    assert r["citations"]
