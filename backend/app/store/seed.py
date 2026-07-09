"""Seed the Northwind Goods store with realistic data.

Deterministic (fixed RNG seed) so demo scenarios always reference the same
orders. The first handful of orders are hand-crafted to cover the edge cases
the agent's acceptance tests rely on; the rest are generated across all
statuses. Re-running clears and re-seeds.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, init_db
from app.db.models import Customer, Order, OrderItem, Refund, Shipment

random.seed(42)

NOW = datetime.now(timezone.utc)

FIRST_NAMES = ["Ava", "Liam", "Mia", "Noah", "Zoe", "Ethan", "Lucia", "Owen",
               "Priya", "Marcus", "Sofia", "Diego", "Hana", "Jonas", "Ivy", "Ben"]
LAST_NAMES = ["Reyes", "Kim", "Novak", "Okafor", "Silva", "Andersson", "Patel",
              "Rossi", "Nguyen", "Weber", "Haddad", "Lindqvist", "Costa", "Yamamoto"]
PRODUCTS = [
    ("Aurora Desk Lamp", 4200), ("Trailhead Backpack", 8900), ("Cirrus Wireless Earbuds", 12900),
    ("Meadow Ceramic Mug", 1800), ("Summit Water Bottle", 2400), ("Nimbus Throw Blanket", 5600),
    ("Harbor Rain Jacket", 11200), ("Fern Potting Kit", 3300), ("Pico Mechanical Keyboard", 15900),
    ("Drift Linen Sheets", 8800), ("Bramble Scented Candle", 2200), ("Onyx Travel Charger", 3900),
]
CARRIERS = ["UPS", "FedEx", "USPS", "DHL"]
CITIES = ["221B Baker St, Springfield", "88 Larkspur Ln, Portland", "5 Cedar Ct, Austin",
          "12 Wharf Rd, Seattle", "40 Juniper Ave, Denver"]


def _addr() -> str:
    return random.choice(CITIES)


def _order(db: Session, oid: str, cust: Customer, status: str, days_ago_placed: int,
           items: list[tuple[str, int, int]], delivered_days_ago: int | None = None,
           shipment_status: str | None = None, eta_days: int | None = None,
           refunded: bool = False) -> Order:
    placed = NOW - timedelta(days=days_ago_placed)
    total = sum(q * p for _, q, p in items)
    delivered = NOW - timedelta(days=delivered_days_ago) if delivered_days_ago is not None else None
    order = Order(
        id=oid, customer_id=cust.id, status=status, total_cents=total,
        currency="USD", placed_at=placed, delivered_at=delivered, shipping_address=_addr(),
    )
    db.add(order)
    db.flush()
    for name, qty, price in items:
        db.add(OrderItem(order_id=oid, product_name=name, qty=qty, unit_price_cents=price))
    if shipment_status is not None:
        eta = NOW + timedelta(days=eta_days) if eta_days is not None else None
        db.add(Shipment(
            order_id=oid, carrier=random.choice(CARRIERS),
            tracking_number=f"1Z{random.randint(10**9, 10**10 - 1)}",
            status=shipment_status, eta=eta,
        ))
    if refunded:
        db.add(Refund(order_id=oid, amount_cents=total, reason="Customer return — item defective"))
    return order


def seed(db: Session) -> dict:
    # Clear existing (respect FK order)
    for model in (Refund, Shipment, OrderItem, Order, Customer):
        db.execute(delete(model))
    db.commit()

    customers: list[Customer] = []
    for i in range(15):
        fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        c = Customer(name=f"{fn} {ln}", email=f"{fn.lower()}.{ln.lower()}{i}@example.com",
                     created_at=NOW - timedelta(days=random.randint(60, 400)))
        db.add(c)
        customers.append(c)
    db.commit()

    # Named customer for demo scenarios.
    demo = customers[0]
    demo.name = "Ava Reyes"
    demo.email = "ava.reyes@example.com"
    db.commit()

    counter = 1

    def oid() -> str:
        nonlocal counter
        s = f"ORD-{counter:05d}"
        counter += 1
        return s

    # --- Hand-crafted edge cases (stable ids the demo scenarios reference) ---
    # ORD-00001..6 filler for realism
    for _ in range(6):
        _order(db, oid(), random.choice(customers), "delivered", 45,
               [(random.choice(PRODUCTS)[0], 1, random.choice(PRODUCTS)[1])],
               delivered_days_ago=40, shipment_status="delivered")

    # ORD-00007 — DELIVERED, eligible for refund, UNDER threshold (~$56)
    _order(db, oid(), demo, "delivered", 8,
           [("Nimbus Throw Blanket", 1, 5600)], delivered_days_ago=5, shipment_status="delivered")

    # ORD-00008 — already refunded
    _order(db, oid(), demo, "refunded", 20,
           [("Meadow Ceramic Mug", 2, 1800)], delivered_days_ago=15,
           shipment_status="delivered", refunded=True)

    # ORD-00009 — delivered but OUTSIDE the 30-day window (~45 days)
    _order(db, oid(), demo, "delivered", 50,
           [("Harbor Rain Jacket", 1, 11200)], delivered_days_ago=45, shipment_status="delivered")

    # ORD-00010 — still processing (cancellable, not refundable)
    _order(db, oid(), demo, "processing", 1,
           [("Fern Potting Kit", 1, 3300), ("Bramble Scented Candle", 2, 2200)])

    # ORD-00011 — delayed shipment
    _order(db, oid(), customers[2], "shipped", 4,
           [("Pico Mechanical Keyboard", 1, 15900)], shipment_status="delayed", eta_days=6)

    # ORD-00012 — the canonical "where's my order" (in transit, ETA soon)
    _order(db, oid(), demo, "shipped", 3,
           [("Cirrus Wireless Earbuds", 1, 12900)], shipment_status="in_transit", eta_days=2)

    # ORD-00013 — HIGH VALUE delivered, eligible refund, OVER threshold (~$318) -> needs approval
    _order(db, oid(), demo, "delivered", 6,
           [("Pico Mechanical Keyboard", 2, 15900)], delivered_days_ago=4, shipment_status="delivered")

    # ORD-00014 — out for delivery
    _order(db, oid(), customers[3], "shipped", 2,
           [("Trailhead Backpack", 1, 8900)], shipment_status="out_for_delivery", eta_days=1)

    # --- Bulk fill to ~40 orders across statuses ---
    statuses = ["processing", "shipped", "delivered", "delivered", "delivered", "cancelled"]
    while counter <= 40:
        cust = random.choice(customers)
        status = random.choice(statuses)
        n_items = random.randint(1, 3)
        items = [(p[0], random.randint(1, 2), p[1]) for p in random.sample(PRODUCTS, n_items)]
        if status == "processing":
            _order(db, oid(), cust, status, random.randint(0, 2), items)
        elif status == "shipped":
            _order(db, oid(), cust, status, random.randint(2, 6), items,
                   shipment_status=random.choice(["in_transit", "out_for_delivery", "delayed"]),
                   eta_days=random.randint(1, 5))
        elif status == "cancelled":
            _order(db, oid(), cust, status, random.randint(3, 20), items)
        else:  # delivered
            dd = random.randint(2, 60)
            _order(db, oid(), cust, status, dd + random.randint(2, 5), items,
                   delivered_days_ago=dd, shipment_status="delivered")

    db.commit()

    n_orders = db.query(Order).count()
    n_customers = db.query(Customer).count()
    return {"customers": n_customers, "orders": n_orders}


def seed_if_empty(db: Session) -> dict | None:
    """Seed only when the store is empty — safe to call on every boot against a
    persistent database (Supabase) without wiping live changes."""
    if db.query(Customer).count() > 0:
        return None
    return seed(db)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        result = seed(db)
        print(f"Seeded Northwind Goods: {result['customers']} customers, {result['orders']} orders.")
        print("Demo customer: ava.reyes@example.com")
        print("Key orders: ORD-00007 (refund-eligible), ORD-00012 (in transit), "
              "ORD-00013 (>threshold refund), ORD-00009 (out of window), ORD-00010 (processing).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
