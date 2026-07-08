"""Pydantic request/response schemas for the store REST API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RefundRequest(BaseModel):
    amount_cents: int = Field(gt=0, description="Refund amount in cents.")
    reason: str = Field(default="", max_length=500)


class AddressUpdateRequest(BaseModel):
    new_address: str = Field(min_length=3, max_length=300)


class ErrorResponse(BaseModel):
    error: str
    code: str
