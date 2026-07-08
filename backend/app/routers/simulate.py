"""Simulation endpoint — replays the golden tickets live through the agent.

Turns an empty dashboard into a populated one on demand: a visitor clicks
"Run simulation" and watches conversations get created, resolved, and escalated
while metric cards climb. Streams progress over SSE (robust and simple); each
ticket is tagged source="simulation" so "Reset demo" can clear them.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import reset_session, run_agent
from app.db.database import SessionLocal
from app.db.models import Conversation
from app.store.seed import seed
from eval.judge import judge_ticket

router = APIRouter(prefix="/simulate", tags=["simulation"])

_TICKETS = Path(__file__).resolve().parents[2] / "eval" / "golden_tickets.yaml"


def _load(limit: int | None) -> list[dict]:
    tickets = yaml.safe_load(_TICKETS.read_text(encoding="utf-8"))
    return tickets[:limit] if limit else tickets


@router.get("/stream")
async def simulate_stream(limit: int = 20):
    """SSE stream: one event per ticket as it resolves, plus a final summary."""
    tickets = _load(limit)

    async def gen():
        loop = asyncio.get_event_loop()
        counts = {"resolved": 0, "escalated": 0, "pending_approval": 0}
        yield {"event": "start", "data": json.dumps({"total": len(tickets)})}

        for i, ticket in enumerate(tickets):
            result = await loop.run_in_executor(None, _run_ticket, ticket)
            counts[result["outcome"]] = counts.get(result["outcome"], 0) + 1
            payload = {
                "index": i + 1, "total": len(tickets), "ticket_id": ticket["id"],
                "category": ticket["category"], "outcome": result["outcome"],
                "conversation_id": result.get("conversation_id"),
                "preview": ticket["messages"][-1][:80],
                "cost_usd": result.get("cost_usd", 0), "counts": dict(counts),
            }
            yield {"event": "ticket", "data": json.dumps(payload)}
            await asyncio.sleep(0.05)  # let the UI animate

        yield {"event": "done", "data": json.dumps({"total": len(tickets), "counts": counts})}

    return EventSourceResponse(gen())


def _run_ticket(ticket: dict) -> dict:
    """Run one ticket to completion on its own DB session (executor thread)."""
    db = SessionLocal()
    try:
        seed(db)
        sid = f"sim-{ticket['id']}"
        reset_session(sid)
        result = {"outcome": "open", "conversation_id": None, "cost_usd": 0}
        for msg in ticket["messages"]:
            result = run_agent(db, sid, msg, source="simulation")
        # Score the resolution so the dashboard shows a real judge score.
        scores = judge_ticket(ticket, result)
        if result.get("conversation_id"):
            conv = db.get(Conversation, result["conversation_id"])
            if conv:
                conv.judge_score = round(scores["overall"] * 5, 2)
                conv.judge_detail = scores
                db.commit()
        return result
    finally:
        db.close()
