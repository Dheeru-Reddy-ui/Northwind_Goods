"""Guardrails: PII redaction + input/output safety.

Phase 1 ships redaction (used by the tracer) and a basic input check. Phase 3
expands the input guardrail (prompt-injection, abuse, off-topic) and adds an
output guardrail. Keeping the interfaces stable means the graph doesn't change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
PHONE_RE = re.compile(r"\b(?:\+?\d[\d -]{8,}\d)\b")


def _redact_text(text: str) -> str:
    text = EMAIL_RE.sub("[redacted-email]", text)
    text = CARD_RE.sub("[redacted-card]", text)
    return text


def redact_pii(obj):
    """Recursively redact PII from a str / dict / list so it's safe to persist.

    Order ids and tracking numbers are intentionally preserved — they're
    operational identifiers the ops team needs, not personal data.
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        return _redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact_pii(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_pii(v) for v in obj]
    return obj


@dataclass
class GuardVerdict:
    blocked: bool
    reason: str = ""
    category: str = "ok"
    safe_reply: str = ""


# Prompt-injection / jailbreak attempts — refuse and stay in role.
INJECTION_MARKERS = (
    "ignore your instructions", "ignore all previous", "ignore previous", "disregard your",
    "disregard all", "system prompt", "you are now", "act as", "developer mode", "jailbreak",
    "reveal your prompt", "print your instructions", "show me your prompt", "repeat the words above",
    "100% discount", "free money", "override your", "new instructions:",
)
# Attempts to exfiltrate other customers' data or internals.
EXFIL_MARKERS = (
    "all orders", "all customers", "everyone's", "other customers", "admin password",
    "database", "list all", "dump", "every order in",
)

INJECTION_REPLY = (
    "I can't do that — I follow Northwind Goods policy and can't change my instructions or make "
    "exceptions like that. I'm happy to help with your own orders though: checking status, refunds "
    "within policy, address changes, or cancellations. What can I help you with?"
)
EXFIL_REPLY = (
    "For privacy and security I can only help with your own account and orders — I can't look up other "
    "customers' information or internal systems. If you give me your order number I'll gladly help with it."
)


def input_guardrail(message: str) -> GuardVerdict:
    """Block prompt-injection and cross-customer/internal data exfiltration.

    Everything else (including angry or off-topic messages) passes through — the
    agent de-escalates and escalates those rather than refusing outright.
    """
    t = message.lower()
    if any(m in t for m in INJECTION_MARKERS):
        return GuardVerdict(True, reason="prompt-injection attempt", category="injection",
                            safe_reply=INJECTION_REPLY)
    if any(m in t for m in EXFIL_MARKERS):
        return GuardVerdict(True, reason="data-exfiltration attempt", category="exfiltration",
                            safe_reply=EXFIL_REPLY)
    return GuardVerdict(False)


# Phrases that assert a completed refund. If the reply claims one but no
# process_refund tool actually succeeded, the claim is ungrounded -> block.
_REFUND_CLAIM = ("processed your refund", "i've refunded", "i have refunded", "refund has been processed",
                 "refund of", "your refund of", "refunded you", "i've issued", "refund is complete")


def output_guardrail(reply: str, tool_calls: list[dict]) -> GuardVerdict:
    """Block ungrounded action claims and any system-prompt leakage.

    This is a safety net mainly for the LLM path (the deterministic engine's
    replies are always tool-backed). On a violation the graph substitutes the
    safe reply and, upstream, can escalate.
    """
    low = reply.lower()

    # Leaked instructions / persona internals.
    if "operating procedures" in low or "you are the customer support agent" in low:
        return GuardVerdict(True, reason="system-prompt leakage", category="leakage",
                            safe_reply="Sorry — how can I help with your order?")

    # Claims a refund happened without a successful process_refund tool call.
    claims_refund = any(p in low for p in _REFUND_CLAIM)
    did_refund = any(
        tc["tool"] == "process_refund" and (tc.get("output") or {}).get("status") == "processed"
        for tc in tool_calls
    )
    if claims_refund and not did_refund:
        return GuardVerdict(
            True, reason="ungrounded refund claim", category="groundedness",
            safe_reply=("Let me make sure this is handled correctly — I'm routing your refund request to a "
                        "specialist who will confirm the details with you shortly."),
        )
    return GuardVerdict(False)
