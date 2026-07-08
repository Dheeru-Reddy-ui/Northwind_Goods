"""Observability API — conversation list, full traces, and aggregate metrics.

Reads the Postgres/SQLite trace store the agent writes to. LangSmith can run as
an additional backend when LANGSMITH_API_KEY is set (see langsmith_hook); this
store is always present so the dashboard works with no external tracing service.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Conversation, Escalation, PendingAction, TraceStep
from app.observability import analytics

router = APIRouter(prefix="/observability", tags=["observability"])


def _preview(conv: Conversation) -> str:
    for s in conv.steps:
        if s.step_type == "message" and (s.detail or {}).get("role") == "user":
            return (s.detail or {}).get("text", "")[:120]
    return ""


def _summary(conv: Conversation) -> dict:
    tool_steps = [s for s in conv.steps if s.step_type in ("tool", "retrieval", "escalation", "approval_gate")]
    return {
        "id": conv.id,
        "session_id": conv.session_id,
        "channel": conv.channel,
        "source": conv.source,
        "category": conv.category,
        "outcome": conv.outcome,
        "cost_usd": round(conv.cost_usd or 0.0, 6),
        "duration_ms": conv.duration_ms,
        "judge_score": conv.judge_score,
        "customer_email": conv.customer_email,
        "preview": _preview(conv),
        "tool_count": len(tool_steps),
        "step_count": len(conv.steps),
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
    }


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = 0,
    outcome: str | None = None,
    channel: str | None = None,
    source: str | None = None,
) -> dict:
    stmt = select(Conversation).order_by(Conversation.created_at.desc())
    if outcome:
        stmt = stmt.where(Conversation.outcome == outcome)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    if source:
        stmt = stmt.where(Conversation.source == source)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "conversations": [_summary(c) for c in rows]}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, detail={"error": "conversation not found"})
    steps = [{
        "idx": s.idx, "step_type": s.step_type, "label": s.label, "detail": s.detail,
        "latency_ms": s.latency_ms, "cost_usd": round(s.cost_usd or 0.0, 6),
        "tokens_in": s.tokens_in, "tokens_out": s.tokens_out,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    } for s in conv.steps]
    return {**_summary(conv), "steps": steps}


@router.get("/metrics")
def metrics(db: Session = Depends(get_db), hours: int = Query(720, ge=1)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    convs = db.scalars(select(Conversation).where(Conversation.created_at >= since)).all()
    total = len(convs)
    if total == 0:
        return {"total": 0, "resolution_rate": 0, "escalation_rate": 0, "pending_rate": 0,
                "avg_judge_score": None, "avg_cost_usd": 0, "avg_duration_ms": 0,
                "by_category": [], "by_channel": []}

    resolved = sum(1 for c in convs if c.outcome == "resolved")
    escalated = sum(1 for c in convs if c.outcome == "escalated")
    pending = sum(1 for c in convs if c.outcome == "pending_approval")
    judged = [c.judge_score for c in convs if c.judge_score is not None]

    by_cat: dict[str, dict] = {}
    for c in convs:
        cat = c.category or "general"
        d = by_cat.setdefault(cat, {"category": cat, "count": 0, "resolved": 0})
        d["count"] += 1
        d["resolved"] += 1 if c.outcome == "resolved" else 0
    for d in by_cat.values():
        d["resolution_rate"] = round(d["resolved"] / d["count"], 3)

    by_chan: dict[str, dict] = {}
    for c in convs:
        d = by_chan.setdefault(c.channel, {"channel": c.channel, "count": 0})
        d["count"] += 1

    return {
        "total": total,
        "resolution_rate": round(resolved / total, 3),
        "escalation_rate": round(escalated / total, 3),
        "pending_rate": round(pending / total, 3),
        "avg_judge_score": round(sum(judged) / len(judged), 2) if judged else None,
        "avg_cost_usd": round(sum(c.cost_usd or 0 for c in convs) / total, 5),
        "avg_duration_ms": round(sum(c.duration_ms or 0 for c in convs) / total),
        "open_escalations": db.scalar(select(func.count()).select_from(Escalation).where(Escalation.status == "open")),
        "pending_approvals": db.scalar(select(func.count()).select_from(PendingAction).where(PendingAction.status == "pending")),
        "by_category": sorted(by_cat.values(), key=lambda d: -d["count"]),
        "by_channel": list(by_chan.values()),
    }


@router.get("/impact")
def impact(
    db: Session = Depends(get_db),
    human_cost_per_ticket: float = Query(6.0, ge=0),
    human_minutes_per_ticket: float = Query(6.0, ge=0),
    monthly_volume: int = Query(5000, ge=0),
) -> dict:
    return analytics.impact(db, human_cost_per_ticket, human_minutes_per_ticket, monthly_volume)


@router.get("/insights")
def insights(db: Session = Depends(get_db)) -> dict:
    return analytics.insights(db)


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db)) -> dict:
    """Clear simulated conversations (and their traces) so the demo starts fresh.
    Live conversations are kept."""
    sim = db.scalars(select(Conversation).where(Conversation.source == "simulation")).all()
    ids = [c.id for c in sim]
    if ids:
        db.execute(delete(TraceStep).where(TraceStep.conversation_id.in_(ids)))
        db.execute(delete(PendingAction).where(PendingAction.conversation_id.in_(ids)))
        db.execute(delete(Escalation).where(Escalation.conversation_id.in_(ids)))
        db.execute(delete(Conversation).where(Conversation.id.in_(ids)))
        db.commit()
    return {"cleared": len(ids)}
