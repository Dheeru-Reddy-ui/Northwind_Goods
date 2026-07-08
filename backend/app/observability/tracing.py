"""Trace recorder.

A Tracer owns one Conversation row and appends ordered TraceStep rows as the
agent runs, accumulating cost, tokens, and latency. This is the fallback trace
store; LangSmith can run alongside it (see optional integration) but the app is
fully observable without it.

PII redaction of step detail is applied here so nothing sensitive is persisted.
"""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, TraceStep


class Tracer:
    def __init__(self, db: Session, session_id: str, channel: str = "chat",
                 source: str = "live", customer_email: str | None = None):
        self.db = db
        conv = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
        if conv is None:
            conv = Conversation(session_id=session_id, channel=channel, source=source,
                                customer_email=customer_email)
            db.add(conv)
            db.commit()
            db.refresh(conv)
        self.conv = conv
        self._idx = len(conv.steps)
        self._t0 = time.perf_counter()

    @property
    def conversation_id(self) -> str:
        return self.conv.id

    def _redact(self, detail):
        from app.agent.guardrails import redact_pii

        return redact_pii(detail)

    def step(self, step_type: str, label: str, detail=None, latency_ms: int = 0,
             cost_usd: float = 0.0, tokens_in: int = 0, tokens_out: int = 0) -> None:
        s = TraceStep(
            conversation_id=self.conv.id, idx=self._idx, step_type=step_type, label=label,
            detail=self._redact(detail), latency_ms=latency_ms, cost_usd=cost_usd,
            tokens_in=tokens_in, tokens_out=tokens_out,
        )
        self.db.add(s)
        self._idx += 1
        self.conv.cost_usd = (self.conv.cost_usd or 0.0) + cost_usd
        self.db.commit()

    def set_context(self, category: str | None = None, customer_email: str | None = None) -> None:
        if category:
            self.conv.category = category
        if customer_email:
            self.conv.customer_email = customer_email
        self.db.commit()

    def finish(self, outcome: str) -> None:
        self.conv.outcome = outcome
        self.conv.duration_ms = int((time.perf_counter() - self._t0) * 1000)
        self.db.commit()
        self.db.refresh(self.conv)
