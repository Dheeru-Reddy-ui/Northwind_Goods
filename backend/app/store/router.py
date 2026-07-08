"""Store REST endpoints — the store's 'internal systems' the agent acts on.

These mirror the service layer over HTTP. The agent calls the service layer
directly (in-process) rather than through these endpoints, but they exist so
the store is inspectable and so a real deployment could put the store behind
its own network boundary.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.store import service
from app.store.schemas import AddressUpdateRequest, RefundRequest

router = APIRouter(prefix="/store", tags=["store"])


def _handle(fn, *args):
    try:
        return fn(*args)
    except service.StoreError as e:
        status = 404 if e.code == "not_found" else 422
        raise HTTPException(status_code=status, detail={"error": e.message, "code": e.code})


@router.get("/customers/by-email/{email}")
def get_customer(email: str, db: Session = Depends(get_db)):
    return _handle(service.get_customer_by_email, db, email)


@router.get("/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db)):
    order = _handle(service.get_order, db, order_id)
    return service.serialize_order(order, include_customer=True)


@router.get("/orders/{order_id}/shipment")
def get_shipment(order_id: str, db: Session = Depends(get_db)):
    return _handle(service.get_shipment, db, order_id)


@router.get("/orders/{order_id}/refund-eligibility")
def refund_eligibility(order_id: str, db: Session = Depends(get_db)):
    return _handle(service.check_refund_eligibility, db, order_id)


@router.post("/orders/{order_id}/refund")
def refund(order_id: str, body: RefundRequest, db: Session = Depends(get_db)):
    return _handle(service.process_refund, db, order_id, body.amount_cents, body.reason)


@router.patch("/orders/{order_id}/address")
def update_address(order_id: str, body: AddressUpdateRequest, db: Session = Depends(get_db)):
    return _handle(service.update_address, db, order_id, body.new_address)


@router.post("/orders/{order_id}/cancel")
def cancel(order_id: str, db: Session = Depends(get_db)):
    return _handle(service.cancel_order, db, order_id)
