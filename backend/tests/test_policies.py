"""Tests for refund eligibility policy rules."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import Customer, Order, OrderItem
from app.store import policies


def _make_order(db, status="delivered", delivered_days_ago=5, product="Nimbus Throw Blanket", total=5600):
    c = Customer(name="Test User", email="test@example.com")
    db.add(c)
    db.flush()
    delivered = datetime.now(timezone.utc) - timedelta(days=delivered_days_ago) if delivered_days_ago is not None else None
    o = Order(id="ORD-TEST1", customer_id=c.id, status=status, total_cents=total,
              placed_at=datetime.now(timezone.utc) - timedelta(days=(delivered_days_ago or 1) + 2),
              delivered_at=delivered)
    db.add(o)
    db.flush()
    db.add(OrderItem(order_id=o.id, product_name=product, qty=1, unit_price_cents=total))
    db.commit()
    db.refresh(o)
    return o


def test_delivered_within_window_is_eligible(db):
    o = _make_order(db, delivered_days_ago=5)
    eligible, reason = policies.is_refund_eligible(o)
    assert eligible is True
    assert "within" in reason.lower()


def test_delivered_outside_window_is_ineligible(db):
    o = _make_order(db, delivered_days_ago=45)
    eligible, reason = policies.is_refund_eligible(o)
    assert eligible is False
    assert "window" in reason.lower()


def test_already_refunded_is_ineligible(db):
    o = _make_order(db, status="refunded")
    eligible, reason = policies.is_refund_eligible(o)
    assert eligible is False


def test_processing_order_is_ineligible(db):
    o = _make_order(db, status="processing", delivered_days_ago=None)
    eligible, reason = policies.is_refund_eligible(o)
    assert eligible is False
    assert "processing" in reason.lower()


def test_non_returnable_item_is_ineligible(db):
    o = _make_order(db, product="$50 Gift Card", delivered_days_ago=2)
    eligible, reason = policies.is_refund_eligible(o)
    assert eligible is False
    assert "non-returnable" in reason.lower()


def test_high_value_requires_approval():
    assert policies.requires_human_approval(policies.REFUND_APPROVAL_THRESHOLD_CENTS + 1) is True
    assert policies.requires_human_approval(policies.REFUND_APPROVAL_THRESHOLD_CENTS - 1) is False
