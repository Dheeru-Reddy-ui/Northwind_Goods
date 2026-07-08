"""Human-in-the-loop approval endpoints (ops side).

High-value refunds are parked as PendingAction rows by the agent instead of
auto-executing. An ops user approves or rejects them here. Approval executes the
action through the same rule-enforced service layer (eligibility is re-checked),
so approval can't push an out-of-policy refund through either.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Conversation, PendingAction, TraceStep
from app.store import service

router = APIRouter(prefix="/actions", tags=["actions"])


def _serialize(pa: PendingAction) -> dict:
    return {
        "id": pa.id, "action": pa.action, "args": pa.args, "reason": pa.reason,
        "status": pa.status, "conversation_id": pa.conversation_id,
        "created_at": pa.created_at.isoformat() if pa.created_at else None,
    }


@router.get("/pending")
def list_pending(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(PendingAction).where(PendingAction.status == "pending").order_by(PendingAction.created_at.desc())
    ).all()
    return [_serialize(pa) for pa in rows]


def _get(db: Session, action_id: str) -> PendingAction:
    pa = db.get(PendingAction, action_id)
    if pa is None:
        raise HTTPException(404, detail={"error": "pending action not found"})
    if pa.status != "pending":
        raise HTTPException(409, detail={"error": f"action already {pa.status}"})
    return pa


def _trace(db: Session, conversation_id: str | None, step_type: str, label: str, detail: dict) -> None:
    if not conversation_id:
        return
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        return
    db.add(TraceStep(conversation_id=conversation_id, idx=len(conv.steps),
                     step_type=step_type, label=label, detail=detail))


@router.post("/{action_id}/approve")
def approve(action_id: str, db: Session = Depends(get_db)) -> dict:
    pa = _get(db, action_id)
    if pa.action != "process_refund":
        raise HTTPException(422, detail={"error": f"cannot execute action '{pa.action}'"})
    args = pa.args
    try:
        result = service.process_refund(db, args["order_id"], args["amount_cents"], args.get("reason", ""))
    except service.StoreError as e:
        raise HTTPException(422, detail={"error": e.message, "code": e.code})

    pa.status = "approved"
    pa.resolved_at = datetime.now(timezone.utc)
    if pa.conversation_id:
        conv = db.get(Conversation, pa.conversation_id)
        if conv and conv.outcome == "pending_approval":
            conv.outcome = "resolved"
    _trace(db, pa.conversation_id, "approval_gate", "Human approved refund",
           {"decision": "approved", "result": result})
    db.commit()
    return {"status": "approved", "result": result}


@router.post("/{action_id}/reject")
def reject(action_id: str, db: Session = Depends(get_db)) -> dict:
    pa = _get(db, action_id)
    pa.status = "rejected"
    pa.resolved_at = datetime.now(timezone.utc)
    if pa.conversation_id:
        conv = db.get(Conversation, pa.conversation_id)
        if conv and conv.outcome == "pending_approval":
            conv.outcome = "escalated"
    _trace(db, pa.conversation_id, "approval_gate", "Human rejected refund", {"decision": "rejected"})
    db.commit()
    return {"status": "rejected"}
