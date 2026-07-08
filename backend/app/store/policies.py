"""Store policy encoded as data + rules.

Single source of truth for business rules. Both the store REST endpoints and
the agent's `check_refund_eligibility` tool call `is_refund_eligible` so the
rule can never be bypassed by going through the agent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.db.models import Order

RETURN_WINDOW_DAYS = settings.return_window_days
FREE_SHIPPING_THRESHOLD_CENTS = 5000
STANDARD_SHIPPING_SLA_DAYS = 5
EXPRESS_SHIPPING_SLA_DAYS = 2
REFUND_APPROVAL_THRESHOLD_CENTS = settings.refund_approval_threshold_cents

# Items that are never returnable regardless of the window.
NON_RETURNABLE_KEYWORDS = ("gift card", "final sale", "perishable")


def _reference_date(order: Order) -> datetime:
    """Date the return window counts from: delivery date if known, else placed."""
    ref = order.delivered_at or order.placed_at
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref


def is_refund_eligible(order: Order) -> tuple[bool, str]:
    """Return (eligible, human-readable reason) for refunding an order.

    Rules, in order:
      * cancelled / already-refunded orders cannot be refunded again
      * non-returnable items block the refund
      * orders still processing are cancellable, not refundable
      * the delivery/purchase date must fall within the return window
    """
    if order.status == "refunded":
        return False, "This order has already been refunded."
    if order.status == "cancelled":
        return False, "This order was cancelled and cannot be refunded."

    for item in order.items:
        name = item.product_name.lower()
        if any(k in name for k in NON_RETURNABLE_KEYWORDS):
            return False, f"'{item.product_name}' is a non-returnable item (final sale)."

    if order.status == "processing":
        return (
            False,
            "This order is still processing and has not been paid out; cancel it instead of refunding.",
        )

    ref = _reference_date(order)
    days_since = (datetime.now(timezone.utc) - ref).days
    if days_since > RETURN_WINDOW_DAYS:
        return (
            False,
            f"This order is outside the {RETURN_WINDOW_DAYS}-day return window "
            f"({days_since} days since delivery).",
        )

    return True, f"Eligible: within the {RETURN_WINDOW_DAYS}-day return window ({days_since} days ago)."


def requires_human_approval(amount_cents: int) -> bool:
    """High-value refunds route to a human instead of auto-executing."""
    return amount_cents > REFUND_APPROVAL_THRESHOLD_CENTS


def can_modify_order(order: Order) -> tuple[bool, str]:
    """Address changes and cancellations are only allowed before shipment."""
    if order.status in ("processing",):
        return True, "Order has not shipped yet."
    return False, f"Order is '{order.status}' and can no longer be modified before shipment."
