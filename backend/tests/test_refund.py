"""Tests for the refund service path (success + rejection)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Customer, Order, OrderItem
from app.store import service


def _order(db, status="delivered", delivered_days_ago=5, total=5600):
    c = Customer(name="Buyer", email="buyer@example.com")
    db.add(c)
    db.flush()
    delivered = datetime.now(timezone.utc) - timedelta(days=delivered_days_ago) if delivered_days_ago is not None else None
    o = Order(id="ORD-00007", customer_id=c.id, status=status, total_cents=total,
              placed_at=datetime.now(timezone.utc) - timedelta(days=8), delivered_at=delivered)
    db.add(o)
    db.flush()
    db.add(OrderItem(order_id=o.id, product_name="Nimbus Throw Blanket", qty=1, unit_price_cents=total))
    db.commit()
    return o


def test_eligible_refund_succeeds_and_records(db):
    _order(db, delivered_days_ago=5)
    result = service.process_refund(db, "ORD-00007", 5600, "Customer changed mind")
    assert result["order_status"] == "refunded"
    assert result["amount_cents"] == 5600
    # A refund record now exists.
    elig = service.check_refund_eligibility(db, "ORD-00007")
    assert elig["eligible"] is False  # already refunded


def test_out_of_window_refund_is_rejected(db):
    _order(db, delivered_days_ago=45)
    with pytest.raises(service.StoreError) as exc:
        service.process_refund(db, "ORD-00007", 5600, "Too late")
    assert exc.value.code == "refund_ineligible"


def test_refund_over_total_is_rejected(db):
    _order(db, delivered_days_ago=5, total=5600)
    with pytest.raises(service.StoreError) as exc:
        service.process_refund(db, "ORD-00007", 999999, "Too much")
    assert exc.value.code == "invalid_amount"


def test_cancel_only_before_shipment(db):
    _order(db, status="delivered", delivered_days_ago=2)
    with pytest.raises(service.StoreError):
        service.cancel_order(db, "ORD-00007")
