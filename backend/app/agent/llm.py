"""Thin, swappable LLM provider interface.

The agent loop talks to a provider through one method — `next_step` — which
returns either a set of tool calls or a final answer, plus token/cost usage.
Two implementations:

  * AnthropicProvider   — real Claude via the Anthropic SDK (used when
                          ANTHROPIC_API_KEY is set).
  * DeterministicProvider — a rule-based planner that runs the SAME tool-calling
                          loop with no network or key, so the whole product is
                          demoable offline. It estimates token/cost at Claude
                          rates so the observability dashboards stay meaningful
                          (clearly tagged provider="deterministic").

Swapping providers is a one-line change in get_llm(); nothing else in the agent
knows which model is behind the interface.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.config import settings

# Approximate USD per 1M tokens. Used for real Claude and for the offline
# estimate. Keep this in one place so cost accounting is consistent.
PRICE_PER_MTOK = {
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "_default": (3.0, 15.0),
}


def price_for(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICE_PER_MTOK.get(model, PRICE_PER_MTOK["_default"])
    return (tokens_in / 1_000_000) * pin + (tokens_out / 1_000_000) * pout


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass
class ToolCall:
    name: str
    input: dict
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Step:
    """One decision from the model: call tools, or produce the final answer."""

    kind: str  # "tool_use" | "final"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for the offline cost model."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic  # imported lazily so the package is optional

        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def next_step(self, system: str, messages: list[dict], tools: list[dict]) -> Step:
        anthropic_messages = _to_anthropic_messages(messages)
        resp = self.client.messages.create(
            model=self.model,
            system=system,
            messages=anthropic_messages,
            tools=tools,
            max_tokens=1024,
        )
        usage = Usage(
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
            cost_usd=price_for(self.model, resp.usage.input_tokens, resp.usage.output_tokens),
        )
        text_parts, tool_calls = [], []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(name=block.name, input=dict(block.input), id=block.id))
        if tool_calls:
            return Step(kind="tool_use", text="".join(text_parts), tool_calls=tool_calls, usage=usage)
        return Step(kind="final", text="".join(text_parts), usage=usage)


class DeterministicProvider:
    """Offline planner. Delegates the actual decision to the deterministic engine."""

    name = "deterministic"

    def __init__(self) -> None:
        self.model = settings.anthropic_model  # used only for the cost estimate

    def next_step(self, system: str, messages: list[dict], tools: list[dict]) -> Step:
        from app.agent import deterministic

        step = deterministic.plan_next_step(messages, tools)
        # Estimate usage at Claude rates so dashboards show representative cost.
        tin = estimate_tokens(system) + sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        tout = estimate_tokens(step.text) + 40 * len(step.tool_calls)
        step.usage = Usage(tokens_in=tin, tokens_out=tout, cost_usd=price_for(self.model, tin, tout))
        return step


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """Convert the provider-agnostic message list to Anthropic content blocks."""
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "content": m["content"]})
        elif role == "assistant":
            content = []
            if m.get("content"):
                content.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls", []):
                content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})
            out.append({"role": "assistant", "content": content})
        elif role == "tool":
            out.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m["tool_call_id"],
                    "content": str(m["content"]),
                }],
            })
    return out


def get_llm():
    """Factory: real Claude if a key is present, else the deterministic engine."""
    if settings.llm_available:
        try:
            return AnthropicProvider()
        except Exception as e:  # missing package / bad key -> graceful fallback
            print(f"[llm] Anthropic unavailable ({e}); falling back to deterministic engine.")
    return DeterministicProvider()
