"""Deterministic reasoning engine (offline planner).

Drives the exact same tool-calling loop as the LLM path, but decides the next
step with rules instead of a model. It reads the provider-agnostic message
list — the current user message plus any tool results gathered this turn — and
returns the next `Step` (a tool call, or the final answer).

This is intentionally a small, legible state machine per intent. It is not a
replacement for the LLM's reasoning; it exists so the product runs end-to-end
with no API key, and so the deterministic path can be A/B'd against Claude.
"""
from __future__ import annotations

import re

from app.agent.llm import Step, ToolCall

ORD_RE = re.compile(r"ORD-?0*(\d{1,5})", re.IGNORECASE)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

INJECTION_MARKERS = (
    "ignore your instructions", "ignore previous", "ignore all previous", "system prompt",
    "you are now", "developer mode", "disregard your", "100% discount", "free money",
    "reveal your prompt", "print your instructions", "jailbreak",
)
ESCALATION_MARKERS = (
    "lawyer", "sue you", "i'll sue", "legal action", "attorney", "chargeback", "charge back",
    "reporting you", "report you", "bbb", "better business bureau", "fraud", "press charges",
    "speak to a human", "talk to a human", "speak to a manager", "real person", "human agent",
)
DISTRESS_MARKERS = (
    "unacceptable", "ridiculous", "furious", "outrageous", "worst", "terrible", "disgusting",
    "never again", "third time", "3rd time", "fed up", "sick of",
)
REFUND_MARKERS = ("refund", "money back", "my money", "reimburse", "give me back")
CANCEL_MARKERS = ("cancel",)
ADDRESS_MARKERS = ("address", "change delivery", "change the delivery", "ship it to", "deliver it to", "reroute")
STATUS_MARKERS = ("where", "track", "status", "when will", "arrive", "delivered yet", "shipped", "eta", "delivery")
POLICY_MARKERS = (
    "policy", "return window", "how long", "how many days", "warranty", "damaged", "broken",
    "hours", "open", "international", "shipping cost", "how much is shipping", "do you ship",
    "can i return", "non-returnable", "exchange", "gift card",
)
GREETING_MARKERS = (
    "hello", "hi ", "hey", "good morning", "good afternoon", "good evening",
    "can you help", "what can you do", "who are you", "what do you do", "thanks", "thank you",
)
# Informational framing -> a policy question, not an action request.
QUESTION_MARKERS = (
    "how long", "how many", "how do", "how much", "what is", "what's", "what are",
    "when will", "when do", "do you", "are there", "is there", "can i return",
    "can i get", "what happens", "policy", "how does",
)


def _norm_order_id(text: str) -> str | None:
    m = ORD_RE.search(text)
    if not m:
        return None
    return f"ORD-{int(m.group(1)):05d}"


def _has(text: str, markers) -> bool:
    return any(m in text for m in markers)


def _detect_intent(text: str) -> str:
    t = text.lower()
    if _has(t, INJECTION_MARKERS):
        return "injection"
    if _has(t, ESCALATION_MARKERS):
        return "escalation"
    # Angry + multi-part complaint -> escalate.
    if _has(t, DISTRESS_MARKERS) and (_has(t, REFUND_MARKERS) or t.count("order") > 1):
        return "escalation"
    # With a concrete order id, treat it as an action/status request on that order.
    if _norm_order_id(t):
        if _has(t, REFUND_MARKERS):
            return "refund"
        if _has(t, ADDRESS_MARKERS):
            return "address_change"
        if _has(t, CANCEL_MARKERS):
            return "cancel"
        return "order_status"

    # No order id: an informational question about policy beats an action verb
    # ("how long do refunds take" is a question, "I want a refund" is an action).
    if _has(t, QUESTION_MARKERS) or _has(t, POLICY_MARKERS):
        return "policy_qa"
    if _has(t, REFUND_MARKERS):
        return "refund"
    if _has(t, CANCEL_MARKERS):
        return "cancel"
    if _has(t, ADDRESS_MARKERS):
        return "address_change"
    if _has(t, STATUS_MARKERS):
        return "order_status"
    if _has(t, GREETING_MARKERS):
        return "smalltalk"
    if "?" in t:
        return "policy_qa"
    return "smalltalk"


def _parse(messages: list[dict]) -> tuple[str, dict]:
    """Return (current user text, {tool_name: [results this turn]})."""
    last_user_idx = max(
        (i for i, m in enumerate(messages) if m["role"] == "user"), default=0
    )
    user_text = messages[last_user_idx]["content"]
    if isinstance(user_text, list):  # defensive
        user_text = " ".join(str(x) for x in user_text)
    results: dict[str, list] = {}
    for m in messages[last_user_idx + 1:]:
        if m["role"] == "tool":
            results.setdefault(m["name"], []).append(m["content"])
    return user_text, results


def _tc(name: str, **kwargs) -> Step:
    return Step(kind="tool_use", tool_calls=[ToolCall(name=name, input=kwargs)])


def _final(text: str) -> Step:
    return Step(kind="final", text=text)


# ---------------------------------------------------------------------------
# Per-intent planners
# ---------------------------------------------------------------------------
def plan_next_step(messages: list[dict], tools: list[dict]) -> Step:
    user_text, results = _parse(messages)
    intent = _detect_intent(user_text)
    order_id = _norm_order_id(user_text)

    if intent == "injection":
        return _final(
            "I'm not able to do that. I can only help with your Northwind Goods orders — "
            "checking status, refunds within policy, address changes, and cancellations. "
            "How can I help with your order today?"
        )

    if intent == "escalation":
        if "escalate_to_human" not in results:
            summary = (
                f"Customer message: \"{user_text.strip()[:280]}\". "
                "Customer is distressed and/or raised a legal/chargeback concern that requires human judgment."
            )
            return _tc("escalate_to_human", reason="Distressed customer / legal or chargeback concern", summary=summary)
        return _final(
            "I hear you, and I'm sorry this has been so frustrating — that's not the experience we want you to have. "
            "I've escalated this to a senior specialist with a full summary of your case, and they'll follow up "
            "directly. You won't have to repeat yourself. Is there anything I can note for them in the meantime?"
        )

    if intent == "order_status":
        return _plan_order_status(order_id, results)

    if intent == "refund":
        return _plan_refund(order_id, user_text, results)

    if intent == "address_change":
        return _plan_address(order_id, user_text, results)

    if intent == "cancel":
        return _plan_cancel(order_id, results)

    if intent == "policy_qa":
        return _plan_policy(user_text, results)

    return _final(
        "Hi! I'm the Northwind Goods support assistant. I can check where your order is, "
        "process a refund within policy, change a shipping address before it ships, or cancel an order. "
        "What can I help you with? If you have an order number (like ORD-00012), share it and I'll take a look."
    )


def _plan_order_status(order_id: str | None, results: dict) -> Step:
    if not order_id:
        return _final("Happy to check on that — what's your order number? It looks like ORD-00012.")
    if "lookup_order" not in results:
        return _tc("lookup_order", order_id=order_id)
    order = results["lookup_order"][-1]
    if isinstance(order, dict) and order.get("error"):
        return _final(
            f"I couldn't find an order with the id {order_id}. Could you double-check the number? "
            "It should look like ORD-00012."
        )
    status = order.get("status")
    if status == "processing":
        return _final(
            f"Your order {order_id} is still being processed and hasn't shipped yet. "
            "You'll get a tracking number by email as soon as it's on its way. Anything else I can help with?"
        )
    if status in ("cancelled", "refunded"):
        return _final(f"Order {order_id} is currently marked as **{status}**. Let me know if you'd like details.")
    # shipped/delivered -> check shipment for ETA
    if status == "shipped" and "track_shipment" not in results:
        return _tc("track_shipment", order_id=order_id)
    shipment = results.get("track_shipment", [{}])[-1] if "track_shipment" in results else {}
    return _final(_compose_status(order_id, order, shipment))


def _compose_status(order_id: str, order: dict, shipment: dict) -> str:
    items = ", ".join(f"{i['qty']}× {i['product_name']}" for i in order.get("items", []))
    if order.get("status") == "delivered":
        return (
            f"Good news — order {order_id} ({items}) has been **delivered**. "
            "If anything arrived damaged or you'd like to start a return, just say the word."
        )
    if shipment and not shipment.get("error"):
        eta = shipment.get("eta", "")
        eta_str = f" Estimated delivery is around {eta[:10]}." if eta else ""
        carrier = shipment.get("carrier", "the carrier")
        tn = shipment.get("tracking_number", "")
        st = shipment.get("status", "in transit").replace("_", " ")
        delayed = " I can see it's currently marked as **delayed** — apologies for the wait." if shipment.get("status") == "delayed" else ""
        return (
            f"Your order {order_id} ({items}) is **{st}** with {carrier} "
            f"(tracking {tn}).{eta_str}{delayed} Anything else I can help with?"
        )
    return f"Your order {order_id} ({items}) is currently **{order.get('status')}**."


def _plan_refund(order_id: str | None, user_text: str, results: dict) -> Step:
    if not order_id:
        return _final(
            "I can help with a refund. What's the order number you'd like refunded? "
            "It looks like ORD-00012."
        )
    if "check_refund_eligibility" not in results:
        return _tc("check_refund_eligibility", order_id=order_id)
    elig = results["check_refund_eligibility"][-1]
    if isinstance(elig, dict) and elig.get("error"):
        return _final(f"I couldn't find order {order_id} to check it. Could you confirm the order number?")
    if not elig.get("eligible"):
        reason = elig.get("reason", "It falls outside our refund policy.")
        return _final(
            f"I looked into a refund for {order_id}, but I'm not able to process it: {reason} "
            "I know that's not what you hoped to hear. If the item arrived damaged or defective I can open a "
            "separate claim, or I can connect you with a specialist to review your options — just let me know."
        )
    # eligible
    if "process_refund" not in results:
        amount = elig.get("order_total_cents", 0)
        return _tc("process_refund", order_id=order_id, amount_cents=amount, reason="Customer requested refund")
    res = results["process_refund"][-1]
    status = res.get("status")
    if status == "pending_approval":
        return _final(
            f"Because this refund ({res.get('amount')}) is above our automatic-approval limit, I've submitted it "
            "for a quick human review to protect your account. You'll get a confirmation by email shortly — "
            "you don't need to do anything else. Is there anything else I can help with in the meantime?"
        )
    if status == "processed":
        return _final(
            f"Done — I've processed your refund of **{res.get('amount')}** for order {order_id}. "
            "It'll appear on your original payment method within 5–7 business days. "
            "Sorry for the trouble, and thank you for your patience!"
        )
    return _final(f"I wasn't able to complete that refund: {res.get('reason', 'please contact support.')}")


def _plan_address(order_id: str | None, user_text: str, results: dict) -> Step:
    if "update_shipping_address" not in results:
        new_address = _extract_address(user_text)
        if not new_address:
            return _final(
                f"I can update the delivery address on {order_id} as long as it hasn't shipped. "
                "What's the full new address?"
            )
        return _tc("update_shipping_address", order_id=order_id, new_address=new_address)
    res = results["update_shipping_address"][-1]
    if res.get("status") == "updated":
        return _final(
            f"All set — I've updated the shipping address on {order_id} to **{res.get('shipping_address')}**. "
            "It'll ship to the new address. Anything else?"
        )
    return _final(
        f"I wasn't able to change the address on {order_id}: {res.get('reason', 'it may have already shipped.')} "
        "If it's already on its way, I can help you reroute it with the carrier or start a return once it arrives."
    )


def _plan_cancel(order_id: str | None, results: dict) -> Step:
    if "cancel_order" not in results:
        return _tc("cancel_order", order_id=order_id)
    res = results["cancel_order"][-1]
    if res.get("status") == "cancelled":
        return _final(
            f"Done — order {order_id} has been **cancelled** and you won't be charged. "
            "If you paid already, the hold will drop off in a few business days. Anything else I can do?"
        )
    return _final(
        f"I couldn't cancel {order_id}: {res.get('reason', 'it may have already shipped.')} "
        "If it's shipped, I can help you start a return as soon as it arrives."
    )


def _plan_policy(user_text: str, results: dict) -> Step:
    if "search_knowledge_base" not in results:
        return _tc("search_knowledge_base", query=user_text)
    kb = results["search_knowledge_base"][-1]
    passages = kb.get("passages", []) if isinstance(kb, dict) else []
    if not passages:
        return _final(
            "I don't have that in our policy documents, so I don't want to guess. "
            "I can connect you with a specialist who can confirm — would that help?"
        )
    top = passages[0]
    cite = f"{top['source']}" + (f" › {top['section']}" if top.get("section") else "")
    return _final(
        f"{top['snippet'].strip()}\n\n*Source: {cite}.* "
        "Let me know if you'd like more detail or have a specific order in mind."
    )


def _extract_address(text: str) -> str | None:
    """Best-effort address extraction for 'change my address to ...'."""
    for kw in (" to ", " to:", "address:", "address is "):
        idx = text.lower().find(kw)
        if idx != -1:
            candidate = text[idx + len(kw):].strip(" .")
            if len(candidate) >= 6 and any(ch.isdigit() for ch in candidate):
                return candidate
    return None
