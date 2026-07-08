"""Streaming chat — the glass-box customer experience.

GET /chat/stream runs the SAME agent (tools, guardrails, escalation, tracing)
and streams typed SSE events as it works: friendly activity labels as each step
starts/finishes, then the final answer token by token, then a `done` event with
citations/actions/escalation for the chat to render.

Only customer-safe fields cross this boundary: friendly step labels (not tool
names/args), the agent's reply, and policy citations. Raw tool errors, model
reasoning text, system-prompt internals, and other-customer data never enter
the stream — the full technical detail still flows to the trace store as before.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import run_agent
from app.db.database import SessionLocal

router = APIRouter(tags=["chat"])

# Fields safe to send to the customer (drops tool_calls_made technical I/O).
_SAFE_RESULT_KEYS = (
    "conversation_id", "reply", "outcome", "citations", "actions",
    "pending_actions", "escalations", "cost_usd", "duration_ms",
)


@router.get("/chat/stream")
async def chat_stream(message: str, session_id: str | None = None, channel: str = "chat"):
    sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_event(ev: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def work() -> None:
        db = SessionLocal()
        try:
            result = run_agent(db, sid, message, channel=channel, on_event=on_event)
            safe = {k: result[k] for k in _SAFE_RESULT_KEYS if k in result}
            safe["session_id"] = sid
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "result", "result": safe})
        except Exception:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error"})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "_end"})
            db.close()

    loop.run_in_executor(None, work)

    async def gen():
        while True:
            ev = await queue.get()
            etype = ev.get("type")
            if etype == "_end":
                break
            if etype == "step_started":
                yield {"event": "activity", "data": json.dumps({"label": ev["label"], "status": "active"})}
            elif etype == "step_finished":
                yield {"event": "activity", "data": json.dumps({"label": ev["label"], "status": "done"})}
            elif etype == "final":
                # Stream the (real) answer word by word for a live feel.
                for token in _tokens(ev["text"]):
                    yield {"event": "token", "data": json.dumps({"t": token})}
                    await asyncio.sleep(0.012)
            elif etype == "result":
                yield {"event": "done", "data": json.dumps(ev["result"])}
            elif etype == "error":
                yield {"event": "failed", "data": json.dumps({"message": "The support service had a problem."})}
            # user_message / model events are intentionally not forwarded to the customer.

    return EventSourceResponse(gen())


def _tokens(text: str) -> list[str]:
    """Split into whitespace-preserving chunks so the client can append directly."""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch == " ":
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out
