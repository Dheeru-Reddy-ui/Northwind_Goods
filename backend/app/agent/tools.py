"""Agent tools (function-calling).

Each tool has a Pydantic input schema and an executor that calls the store
service layer directly (in-process, not over HTTP). Executors receive a
ToolContext and record side effects on it — citations, action chips, pending
approvals, escalations — so the graph and tracer can surface them without the
tool result payload having to carry UI concerns.

Business rules are enforced in the service layer, so the agent physically
cannot process an out-of-policy refund even if it tries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Escalation, PendingAction
from app.store import policies, service


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
@dataclass
class ToolContext:
    db: Session
    session_id: str
    conversation_id: str | None = None
    customer_email: str | None = None
    citations: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)         # executed -> chips
    pending: list[dict] = field(default_factory=list)         # awaiting approval
    escalations: list[dict] = field(default_factory=list)
    called_tools: set[str] = field(default_factory=set)       # tools used this turn


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------
class LookupCustomerIn(BaseModel):
    email: str = Field(description="Customer email address.")


class OrderIdIn(BaseModel):
    order_id: str = Field(description="Order id such as ORD-00012.")


class SearchKBIn(BaseModel):
    query: str = Field(description="Natural-language policy or FAQ question.")


class ProcessRefundIn(BaseModel):
    order_id: str = Field(description="Order id such as ORD-00012.")
    amount_cents: int = Field(description="Refund amount in cents. Use the order total for a full refund.")
    reason: str = Field(default="", description="Short reason for the refund.")


class UpdateAddressIn(BaseModel):
    order_id: str
    new_address: str = Field(description="Full new shipping address.")


class EscalateIn(BaseModel):
    reason: str = Field(description="Why this needs a human (e.g. legal threat, chargeback, high distress).")
    summary: str = Field(description="Concise summary of the conversation and recommended next step.")


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------
def _lookup_customer(ctx: ToolContext, email: str) -> dict:
    result = service.get_customer_by_email(ctx.db, email)
    ctx.customer_email = result["email"]
    return result


def _lookup_order(ctx: ToolContext, order_id: str) -> dict:
    order = service.get_order(ctx.db, order_id)
    return service.serialize_order(order, include_customer=True)


def _track_shipment(ctx: ToolContext, order_id: str) -> dict:
    return service.get_shipment(ctx.db, order_id)


def _search_kb(ctx: ToolContext, query: str) -> dict:
    from app.knowledge.retriever import search

    passages = search(ctx.db, query, top_k=3)
    for p in passages:
        ctx.citations.append({"source": p["source"], "section": p["section"], "snippet": p["snippet"]})
    return {"passages": passages, "found": bool(passages)}


def _check_refund_eligibility(ctx: ToolContext, order_id: str) -> dict:
    return service.check_refund_eligibility(ctx.db, order_id)


def _process_refund(ctx: ToolContext, order_id: str, amount_cents: int, reason: str = "") -> dict:
    from app.config import get_settings

    # Reliability safeguard (Track A): require eligibility to have been verified
    # this turn before any refund executes — enforced here, not just in the prompt.
    if get_settings().reliability_fixes and "check_refund_eligibility" not in ctx.called_tools:
        return {"status": "needs_verification",
                "reason": "Call check_refund_eligibility for this order before processing a refund."}

    order = service.get_order(ctx.db, order_id)
    eligible, why = policies.is_refund_eligible(order)
    if not eligible:
        # Rule enforcement: refuse before any write.
        return {"status": "refused", "eligible": False, "reason": why}

    # High-value refunds must not auto-execute — route to a human.
    if policies.requires_human_approval(amount_cents):
        pa = PendingAction(
            conversation_id=ctx.conversation_id,
            session_id=ctx.session_id,
            action="process_refund",
            args={"order_id": order.id, "amount_cents": amount_cents, "reason": reason},
            reason=f"Refund ${amount_cents / 100:.2f} exceeds the "
                   f"${policies.REFUND_APPROVAL_THRESHOLD_CENTS / 100:.2f} auto-approval threshold.",
        )
        ctx.db.add(pa)
        ctx.db.commit()
        ctx.db.refresh(pa)
        pending = {
            "id": pa.id, "action": "process_refund", "order_id": order.id,
            "amount": f"${amount_cents / 100:.2f}", "reason": pa.reason,
        }
        ctx.pending.append(pending)
        return {"status": "pending_approval", **pending}

    result = service.process_refund(ctx.db, order_id, amount_cents, reason)
    ctx.actions.append({"type": "refund", "label": f"Refund processed · {result['amount']}", "detail": result})
    return {"status": "processed", **result}


def _update_address(ctx: ToolContext, order_id: str, new_address: str) -> dict:
    try:
        result = service.update_address(ctx.db, order_id, new_address)
    except service.StoreError as e:
        return {"status": "refused", "reason": e.message}
    ctx.actions.append({"type": "address", "label": "Shipping address updated", "detail": result})
    return {**result, "status": "updated"}


def _cancel_order(ctx: ToolContext, order_id: str) -> dict:
    try:
        result = service.cancel_order(ctx.db, order_id)
    except service.StoreError as e:
        return {"status": "refused", "reason": e.message}
    ctx.actions.append({"type": "cancel", "label": f"Order {order_id} cancelled", "detail": result})
    return {**result, "status": "cancelled"}


def _escalate(ctx: ToolContext, reason: str, summary: str) -> dict:
    esc = Escalation(
        conversation_id=ctx.conversation_id, session_id=ctx.session_id,
        reason=reason, summary=summary,
        recommended_next_step="Human agent to review conversation and follow up with the customer.",
    )
    ctx.db.add(esc)
    ctx.db.commit()
    ctx.db.refresh(esc)
    payload = {"id": esc.id, "reason": reason, "summary": summary}
    ctx.escalations.append(payload)
    return {"status": "escalated", **payload}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
@dataclass
class ToolSpec:
    name: str
    description: str
    schema: type[BaseModel]
    executor: Callable
    kind: str  # read | retrieval | write | escalation
    label: str  # customer-safe activity label

    def anthropic_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema.model_json_schema(),
        }


TOOLS: dict[str, ToolSpec] = {
    "lookup_customer": ToolSpec(
        "lookup_customer", "Look up a customer profile and their orders by email.",
        LookupCustomerIn, _lookup_customer, "read", "Looking up your account"),
    "lookup_order": ToolSpec(
        "lookup_order", "Get full detail for one order: items, status, dates, total.",
        OrderIdIn, _lookup_order, "read", "Looking up your order"),
    "track_shipment": ToolSpec(
        "track_shipment", "Get carrier, tracking number, status and ETA for an order's shipment.",
        OrderIdIn, _track_shipment, "read", "Checking your shipment"),
    "search_knowledge_base": ToolSpec(
        "search_knowledge_base", "Search Northwind policy and FAQ documents; returns passages with citations.",
        SearchKBIn, _search_kb, "retrieval", "Checking our policies"),
    "check_refund_eligibility": ToolSpec(
        "check_refund_eligibility", "Check whether an order is eligible for a refund under policy.",
        OrderIdIn, _check_refund_eligibility, "read", "Checking refund eligibility"),
    "process_refund": ToolSpec(
        "process_refund", "Process a refund. MUST check eligibility first; high-value refunds route to human approval.",
        ProcessRefundIn, _process_refund, "write", "Processing your refund"),
    "update_shipping_address": ToolSpec(
        "update_shipping_address", "Update the shipping address on an order that has not shipped yet.",
        UpdateAddressIn, _update_address, "write", "Updating your shipping address"),
    "cancel_order": ToolSpec(
        "cancel_order", "Cancel an order that has not shipped yet.",
        OrderIdIn, _cancel_order, "write", "Cancelling your order"),
    "escalate_to_human": ToolSpec(
        "escalate_to_human", "Hand off to a human agent with a conversation summary and recommended next step.",
        EscalateIn, _escalate, "escalation", "Connecting you with a specialist"),
}


def anthropic_tool_specs() -> list[dict]:
    return [t.anthropic_schema() for t in TOOLS.values()]


def execute_tool(ctx: ToolContext, name: str, tool_input: dict) -> dict:
    """Validate input against the schema and run the executor. Errors become
    structured tool results the model can react to (not exceptions)."""
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"Unknown tool '{name}'."}
    try:
        validated = spec.schema(**tool_input)
    except Exception as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
    try:
        result = spec.executor(ctx, **validated.model_dump())
        ctx.called_tools.add(name)
        return result
    except service.StoreError as e:
        return {"error": e.message, "code": e.code}
    except Exception as e:  # never crash the loop on a tool failure
        return {"error": f"{name} failed: {e}"}
