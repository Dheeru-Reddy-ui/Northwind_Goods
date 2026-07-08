"""Store service layer — the store's 'internal systems'.

Both the REST endpoints (app/store/router.py) and the agent's tools
(app/agent/tools.py) call these functions directly. Business rules live here
and in policies.py so they cannot be bypassed. Functions return plain dicts
(easy to serialize into tool results and traces) and raise StoreError on
domain violations.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Customer, Order, Refund, Shipment
from app.store import policies


class StoreError(Exception):
    """A domain-rule violation (e.g. refund outside policy). Carries a code."""

    def __init__(self, message: str, code: str = "invalid_request"):
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def serialize_order(order: Order, include_customer: bool = False) -> dict:
    data = {
        "id": order.id,
        "status": order.status,
        "total_cents": order.total_cents,
        "total": f"${order.total_cents / 100:.2f}",
        "currency": order.currency,
        "placed_at": _iso(order.placed_at),
        "delivered_at": _iso(order.delivered_at),
        "shipping_address": order.shipping_address,
        "items": [
            {
                "product_name": i.product_name,
                "qty": i.qty,
                "unit_price_cents": i.unit_price_cents,
                "unit_price": f"${i.unit_price_cents / 100:.2f}",
            }
            for i in order.items
        ],
        "refunds": [
            {"amount_cents": r.amount_cents, "amount": f"${r.amount_cents / 100:.2f}", "reason": r.reason}
            for r in order.refunds
        ],
    }
    if include_customer and order.customer:
        data["customer"] = {"name": order.customer.name, "email": order.customer.email}
    return data


def serialize_shipment(s: Shipment) -> dict:
    return {
        "order_id": s.order_id,
        "carrier": s.carrier,
        "tracking_number": s.tracking_number,
        "status": s.status,
        "eta": _iso(s.eta),
    }


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def get_order(db: Session, order_id: str) -> Order:
    order = db.get(Order, order_id.strip().upper())
    if order is None:
        raise StoreError(f"No order found with id {order_id}.", code="not_found")
    return order


def get_customer_by_email(db: Session, email: str) -> dict:
    customer = db.scalar(select(Customer).where(Customer.email == email.strip().lower()))
    if customer is None:
        raise StoreError(f"No customer found with email {email}.", code="not_found")
    orders = sorted(customer.orders, key=lambda o: o.placed_at, reverse=True)
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "orders": [
            {"id": o.id, "status": o.status, "total": f"${o.total_cents / 100:.2f}", "placed_at": _iso(o.placed_at)}
            for o in orders
        ],
    }


def get_shipment(db: Session, order_id: str) -> dict:
    order = get_order(db, order_id)
    if order.shipment is None:
        raise StoreError(f"Order {order.id} has no shipment yet (status: {order.status}).", code="no_shipment")
    return serialize_shipment(order.shipment)


# ---------------------------------------------------------------------------
# Writes (rule-enforced)
# ---------------------------------------------------------------------------
def process_refund(db: Session, order_id: str, amount_cents: int, reason: str) -> dict:
    """Execute a refund. Enforces eligibility; caller checks the approval threshold."""
    order = get_order(db, order_id)
    eligible, why = policies.is_refund_eligible(order)
    if not eligible:
        raise StoreError(why, code="refund_ineligible")
    if amount_cents <= 0 or amount_cents > order.total_cents:
        raise StoreError(
            f"Refund amount ${amount_cents / 100:.2f} exceeds the order total ${order.total_cents / 100:.2f}.",
            code="invalid_amount",
        )

    refund = Refund(order_id=order.id, amount_cents=amount_cents, reason=reason)
    db.add(refund)
    order.status = "refunded"
    db.commit()
    db.refresh(order)
    return {
        "refund_id": refund.id,
        "order_id": order.id,
        "amount_cents": amount_cents,
        "amount": f"${amount_cents / 100:.2f}",
        "reason": reason,
        "order_status": order.status,
    }


def update_address(db: Session, order_id: str, new_address: str) -> dict:
    order = get_order(db, order_id)
    ok, why = policies.can_modify_order(order)
    if not ok:
        raise StoreError(why, code="not_modifiable")
    order.shipping_address = new_address.strip()
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "shipping_address": order.shipping_address, "status": order.status}


def cancel_order(db: Session, order_id: str) -> dict:
    order = get_order(db, order_id)
    ok, why = policies.can_modify_order(order)
    if not ok:
        raise StoreError(why, code="not_cancellable")
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "status": order.status}


def check_refund_eligibility(db: Session, order_id: str) -> dict:
    order = get_order(db, order_id)
    eligible, reason = policies.is_refund_eligible(order)
    return {
        "order_id": order.id,
        "eligible": eligible,
        "reason": reason,
        "order_total_cents": order.total_cents,
        "requires_approval": policies.requires_human_approval(order.total_cents),
        "approval_threshold_cents": policies.REFUND_APPROVAL_THRESHOLD_CENTS,
    }
