"""Chat endpoint — one turn of the agent per request.

Returns the reply plus the full structured turn: tool calls (input/output),
citations, action chips, pending approvals, and escalation events. This is the
data the frontend renders and the beginning of the conversation's trace.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.graph import run_agent
from app.db.database import get_db

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    channel: str = "chat"


class ChatResponse(BaseModel):
    session_id: str
    conversation_id: str
    reply: str
    outcome: str
    tool_calls_made: list
    citations: list
    actions: list
    pending_actions: list
    escalations: list
    cost_usd: float
    duration_ms: int


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    session_id = body.session_id or f"sess-{uuid.uuid4().hex[:12]}"
    result = run_agent(db, session_id, body.message, channel=body.channel)
    return ChatResponse(session_id=session_id, **result)
