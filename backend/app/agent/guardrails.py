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


def input_guardrail(message: str) -> GuardVerdict:
    """Phase 1: allow everything (full checks land in Phase 3)."""
    return GuardVerdict(blocked=False)


def output_guardrail(reply: str, tool_calls: list[dict]) -> GuardVerdict:
    """Phase 1: pass-through (full checks land in Phase 3)."""
    return GuardVerdict(blocked=False)
