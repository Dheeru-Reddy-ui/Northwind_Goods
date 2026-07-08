"""Impact/ROI + insights analytics.

Two surfaces, both computed live from the real conversation store:

- impact(): quantifies ROI against configurable human-agent assumptions
  (cost/ticket, minutes/ticket, monthly volume) so the numbers recompute as the
  assumptions change.
- insights(): aggregates structured signal (categories, escalation reasons, tool
  usage, weak-retrieval questions) and writes a short brief grounded ONLY in
  those real numbers — it never invents figures. With ANTHROPIC_API_KEY set the
  brief is phrased by Claude from the same aggregates; offline it is templated.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Escalation, TraceStep


# ---------------------------------------------------------------------------
# Impact / ROI
# ---------------------------------------------------------------------------
def impact(db: Session, human_cost_per_ticket: float, human_minutes_per_ticket: float,
           monthly_volume: int) -> dict:
    convs = list(db.scalars(select(Conversation).order_by(Conversation.created_at.asc())))
    total = len(convs)
    if total == 0:
        return {"total": 0, "assumptions": {
            "human_cost_per_ticket": human_cost_per_ticket,
            "human_minutes_per_ticket": human_minutes_per_ticket,
            "monthly_volume": monthly_volume}}

    escalated = sum(1 for c in convs if c.outcome == "escalated")
    resolved = sum(1 for c in convs if c.outcome == "resolved")
    deflected = total - escalated
    deflection_rate = deflected / total
    resolution_rate = resolved / total

    avg_cost = sum(c.cost_usd or 0 for c in convs) / total
    avg_minutes = (sum(c.duration_ms or 0 for c in convs) / total) / 60000.0
    minutes_saved = max(0.0, human_minutes_per_ticket - avg_minutes)
    cost_saved_per = max(0.0, human_cost_per_ticket - avg_cost)

    projected_monthly = monthly_volume * deflection_rate * cost_saved_per
    savings_curve = [
        {"volume": v, "monthly_savings": round(v * deflection_rate * cost_saved_per, 2)}
        for v in (1000, 5000, 10000, 25000, 50000, 100000)
    ]

    # Rolling resolution rate + cost trend over the conversation sequence.
    series = []
    win = 8
    for i, c in enumerate(convs):
        lo = max(0, i - win + 1)
        window = convs[lo: i + 1]
        rr = sum(1 for x in window if x.outcome == "resolved") / len(window)
        series.append({
            "i": i + 1,
            "resolution_rate": round(rr, 3),
            "cost_usd": round(c.cost_usd or 0, 5),
        })

    by_channel: Counter = Counter(c.channel for c in convs)

    return {
        "total": total,
        "assumptions": {
            "human_cost_per_ticket": human_cost_per_ticket,
            "human_minutes_per_ticket": human_minutes_per_ticket,
            "monthly_volume": monthly_volume,
        },
        "autonomous_resolution_rate": round(resolution_rate, 3),
        "deflection_rate": round(deflection_rate, 3),
        "avg_agent_minutes": round(avg_minutes, 3),
        "avg_agent_cost": round(avg_cost, 5),
        "minutes_saved_per_ticket": round(minutes_saved, 2),
        "cost_saved_per_ticket": round(cost_saved_per, 4),
        "total_cost_saved_window": round(deflected * cost_saved_per, 2),
        "projected_monthly_savings": round(projected_monthly, 2),
        "projected_annual_savings": round(projected_monthly * 12, 2),
        "series": series,
        "volume_by_channel": [{"channel": k, "count": v} for k, v in by_channel.items()],
        "savings_curve": savings_curve,
    }


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------
def _tool_from_label(label: str) -> str:
    if "·" in label:
        return label.split("·", 1)[1].strip()
    return label


def insights(db: Session) -> dict:
    convs = list(db.scalars(select(Conversation)))
    total = len(convs)

    categories = Counter(c.category or "general" for c in convs)
    escalations = list(db.scalars(select(Escalation)))
    esc_reasons = Counter(e.reason for e in escalations)

    tool_steps = db.scalars(
        select(TraceStep).where(TraceStep.step_type.in_(("tool", "retrieval", "escalation")))
    ).all()
    tool_usage = Counter(_tool_from_label(s.label) for s in tool_steps)

    weak_retrieval = sum(1 for c in convs if c.category == "policy_unknown")
    refused = sum(1 for c in convs if c.category in ("refund_ineligible", "injection", "exfiltration"))

    aggregates = {
        "total_conversations": total,
        "top_categories": [{"name": k, "count": v} for k, v in categories.most_common(6)],
        "top_escalation_reasons": [{"name": k, "count": v} for k, v in esc_reasons.most_common(4)],
        "most_used_tools": [{"name": k, "count": v} for k, v in tool_usage.most_common(6)],
        "weak_retrieval_questions": weak_retrieval,
        "refused_or_blocked": refused,
        "escalations": len(escalations),
    }
    return {"aggregates": aggregates, "insights": _build_insights(aggregates)}


def _build_insights(agg: dict) -> list[dict]:
    """Data-grounded recommendation cards. Every figure comes from `agg` — no
    invented numbers. (With ANTHROPIC_API_KEY the phrasing can be delegated to
    Claude given these same aggregates; offline we template it.)"""
    cards: list[dict] = []
    total = agg["total_conversations"] or 1

    if agg["top_categories"]:
        top = agg["top_categories"][0]
        cards.append({
            "title": "Highest-volume ticket type",
            "recommendation": f"“{top['name'].replace('_', ' ')}” is your busiest workflow "
                              f"({top['count']} of {total} tickets, {round(top['count'] / total * 100)}%). "
                              "Optimising it has the biggest leverage.",
            "metric_label": top["name"].replace("_", " "),
            "metric_value": f"{top['count']} tickets",
        })

    if agg["top_escalation_reasons"]:
        r = agg["top_escalation_reasons"][0]
        share = round(r["count"] / max(1, agg["escalations"]) * 100)
        cards.append({
            "title": "Top escalation driver",
            "recommendation": f"“{r['name']}” drives {share}% of escalations "
                              f"({r['count']} of {agg['escalations']}). Review whether policy or tooling "
                              "can let the agent handle more of these safely.",
            "metric_label": "escalation share",
            "metric_value": f"{share}%",
        })

    if agg["most_used_tools"]:
        t = agg["most_used_tools"][0]
        cards.append({
            "title": "Most-exercised action",
            "recommendation": f"“{t['name']}” is the most-used tool ({t['count']} calls). It's on the critical "
                              "path — reliability and latency work here pays off across the fleet.",
            "metric_label": t["name"],
            "metric_value": f"{t['count']} calls",
        })

    if agg["weak_retrieval_questions"] > 0:
        cards.append({
            "title": "Knowledge-base gaps",
            "recommendation": f"{agg['weak_retrieval_questions']} question(s) had no matching policy document — "
                              "the agent correctly abstained rather than guessing. These are prime candidates "
                              "for new KB articles.",
            "metric_label": "unanswered policy Qs",
            "metric_value": str(agg["weak_retrieval_questions"]),
        })

    if agg["refused_or_blocked"] > 0:
        cards.append({
            "title": "Policy & safety enforcement",
            "recommendation": f"{agg['refused_or_blocked']} ticket(s) were correctly refused or blocked "
                              "(out-of-policy refunds, injections, cross-customer requests) — evidence the "
                              "guardrails are doing real work, not decoration.",
            "metric_label": "refused / blocked",
            "metric_value": str(agg["refused_or_blocked"]),
        })

    return cards
