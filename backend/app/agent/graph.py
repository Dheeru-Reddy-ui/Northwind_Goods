"""The agent loop — a LangGraph-style state machine.

Nodes, conceptually: input guardrail → agent (model) → tools → agent → …
→ output guardrail → finalize. We implement it as an explicit, well-traced
loop rather than pulling in the LangGraph runtime, so the control flow is fully
visible and the loop stays dependency-light and easy to A/B (see Phase 11).
Every node writes a TraceStep and, when streaming, emits a live event.

State (message history + resolved entities) lives in the working message list
plus the ToolContext, and persists across turns via an in-memory session store.
"""
from __future__ import annotations

import time
from typing import Callable

from sqlalchemy.orm import Session

from app.agent import guardrails
from app.agent.llm import get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, ToolContext, anthropic_tool_specs, execute_tool
from app.config import settings
from app.observability.tracing import Tracer

# In-memory conversation history keyed by session_id (text turns only).
# A production deployment would back this with Redis/Postgres; the interface
# is the same.
_SESSIONS: dict[str, list[dict]] = {}

_KIND_TO_STEP = {"read": "tool", "write": "tool", "retrieval": "retrieval", "escalation": "escalation"}


def _emit(cb: Callable | None, event: dict) -> None:
    if cb is not None:
        cb(event)


def _categorize(tool_calls: list[dict], outcome: str) -> str:
    names = [c["tool"] for c in tool_calls]
    if outcome == "escalated":
        return "escalation"
    if outcome == "pending_approval":
        return "refund_approval"
    if "process_refund" in names:
        last = next((c for c in reversed(tool_calls) if c["tool"] == "process_refund"), None)
        if last and last["output"].get("status") == "processed":
            return "refund_eligible"
        if last and last["output"].get("status") == "refused":
            return "refund_ineligible"
    if "check_refund_eligibility" in names:
        return "refund_ineligible"
    if "update_shipping_address" in names:
        return "address_change"
    if "cancel_order" in names:
        return "cancellation"
    if "search_knowledge_base" in names:
        return "policy_qa"
    if "lookup_order" in names or "track_shipment" in names:
        return "order_status"
    return "general"


def run_agent(db: Session, session_id: str, message: str, channel: str = "chat",
              source: str = "live", on_event: Callable | None = None) -> dict:
    """Run one turn of the agent. Returns a structured result and persists a trace."""
    llm = get_llm()
    tracer = Tracer(db, session_id, channel=channel, source=source)
    ctx = ToolContext(db=db, session_id=session_id, conversation_id=tracer.conversation_id)

    history = _SESSIONS.get(session_id, [])
    working: list[dict] = list(history) + [{"role": "user", "content": message}]

    tracer.step("message", "Customer message", {"role": "user", "text": message})
    _emit(on_event, {"type": "user_message", "text": message})

    # --- input guardrail ---
    t0 = time.perf_counter()
    gin = guardrails.input_guardrail(message)
    tracer.step("guardrail", "Input safety check",
                {"verdict": "blocked" if gin.blocked else "ok", "category": gin.category, "reason": gin.reason},
                latency_ms=int((time.perf_counter() - t0) * 1000))
    if gin.blocked:
        reply = gin.safe_reply
        tracer.step("message", "Agent reply", {"role": "assistant", "text": reply})
        outcome = "escalated" if gin.category == "escalate" else "resolved"
        tracer.set_context(category=gin.category)
        tracer.finish(outcome)
        _emit(on_event, {"type": "final", "text": reply})
        _SESSIONS[session_id] = working + [{"role": "assistant", "content": reply}]
        return _result(tracer, reply, [], ctx, outcome)

    tool_calls_made: list[dict] = []
    reply = ""
    hit_cap = True

    for _ in range(settings.max_tool_iterations):
        # cost cap across the session -> escalate instead of continuing
        if tracer.conv.cost_usd > settings.session_cost_cap_usd:
            reply = ("This is taking longer than it should. I'm connecting you with a specialist "
                     "who can finish this for you.")
            execute_tool(ctx, "escalate_to_human",
                         {"reason": "Session cost cap exceeded", "summary": f"Conversation on {session_id} exceeded cost cap."})
            tracer.step("guardrail", "Cost cap reached", {"cost_usd": tracer.conv.cost_usd})
            hit_cap = False
            break

        t0 = time.perf_counter()
        step = llm.next_step(SYSTEM_PROMPT, working, anthropic_tool_specs())
        dt = int((time.perf_counter() - t0) * 1000)
        tracer.step("model", "Agent reasoning",
                    {"text": step.text, "tool_calls": [tc.name for tc in step.tool_calls], "provider": llm.name},
                    latency_ms=dt, cost_usd=step.usage.cost_usd,
                    tokens_in=step.usage.tokens_in, tokens_out=step.usage.tokens_out)
        _emit(on_event, {"type": "model", "text": step.text})

        if step.kind == "final":
            reply = step.text
            hit_cap = False
            break

        working.append({"role": "assistant", "content": step.text, "tool_calls": step.tool_calls})
        for tc in step.tool_calls:
            spec = TOOLS.get(tc.name)
            label = spec.label if spec else tc.name
            step_type = _KIND_TO_STEP.get(spec.kind, "tool") if spec else "tool"
            _emit(on_event, {"type": "step_started", "label": label, "tool": tc.name})

            t0 = time.perf_counter()
            result = execute_tool(ctx, tc.name, tc.input)
            dt = int((time.perf_counter() - t0) * 1000)

            # An approval gate is worth its own node in the trace.
            if result.get("status") == "pending_approval":
                tracer.step("approval_gate", "Routed to human approval",
                            {"input": tc.input, "output": result}, latency_ms=dt)
            else:
                tracer.step(step_type, f"{spec.kind if spec else 'tool'} · {tc.name}",
                            {"input": tc.input, "output": result}, latency_ms=dt)

            _emit(on_event, {"type": "step_finished", "label": label, "tool": tc.name})
            tool_calls_made.append({"tool": tc.name, "input": tc.input, "output": result})
            working.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result})

    if hit_cap and not reply:
        reply = ("I want to make sure this is handled properly, so I'm connecting you with a "
                 "specialist who can help further.")
        execute_tool(ctx, "escalate_to_human",
                     {"reason": "Reached reasoning-step limit", "summary": f"Agent hit step cap on {session_id}."})

    # --- output guardrail ---
    gout = guardrails.output_guardrail(reply, tool_calls_made)
    if gout.blocked:
        reply = gout.safe_reply
        # An ungrounded action claim is a real failure — hand it to a human.
        if gout.category in ("groundedness", "leakage"):
            execute_tool(ctx, "escalate_to_human",
                         {"reason": f"Output guardrail: {gout.reason}",
                          "summary": f"Agent reply failed the {gout.category} check on {session_id}; routed to a human."})
    tracer.step("guardrail", "Output safety check",
                {"verdict": "blocked" if gout.blocked else "ok",
                 "category": gout.category, "reason": gout.reason})

    tracer.step("message", "Agent reply", {"role": "assistant", "text": reply})

    if ctx.escalations:
        outcome = "escalated"
    elif ctx.pending:
        outcome = "pending_approval"
    else:
        outcome = "resolved"

    tracer.set_context(category=_categorize(tool_calls_made, outcome), customer_email=ctx.customer_email)
    tracer.finish(outcome)
    _emit(on_event, {"type": "final", "text": reply})

    _SESSIONS[session_id] = working[: len(history) + 1] + [{"role": "assistant", "content": reply}]
    return _result(tracer, reply, tool_calls_made, ctx, outcome)


def _result(tracer: Tracer, reply: str, tool_calls: list[dict], ctx: ToolContext, outcome: str) -> dict:
    return {
        "conversation_id": tracer.conversation_id,
        "reply": reply,
        "tool_calls_made": tool_calls,
        "citations": ctx.citations,
        "actions": ctx.actions,
        "pending_actions": ctx.pending,
        "escalations": ctx.escalations,
        "outcome": outcome,
        "cost_usd": round(tracer.conv.cost_usd, 6),
        "duration_ms": tracer.conv.duration_ms,
    }


def reset_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)
