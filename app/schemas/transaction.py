"""
schemas/transaction.py — Pydantic v2 schemas for Transaction API endpoints.
These are distinct from the ORM model and can evolve independently.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.transaction import RootCauseCategory, TransactionStatus


# ─── Request schemas ─────────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    """Payload to manually register a new (possibly already-failed) transaction."""
    razorpay_payment_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        examples=["pay_TestCardDeclined001"],
        description="Razorpay payment ID (e.g. pay_XXXXXXXXXXXX)",
    )
    amount: int = Field(
        ...,
        gt=0,
        examples=[50000],
        description="Amount in smallest currency unit (paise for INR, so ₹500 = 50000)",
    )
    currency: str = Field(
        default="INR",
        max_length=8,
        examples=["INR"],
    )
    status: TransactionStatus = Field(
        default=TransactionStatus.FAILED,
        examples=[TransactionStatus.FAILED],
    )
    failure_reason_code: Optional[str] = Field(
        default=None,
        max_length=128,
        examples=["CARD_DECLINED"],
        description="Raw error_reason string from Razorpay (optional at creation time)",
    )
    batch_id: Optional[str] = Field(
        default=None,
        max_length=64,
        examples=["batch_20260825_001"],
        description="Optional batch identifier to scope transactions by run",
    )
    customer_contact: Optional[str] = Field(
        default=None,
        max_length=32,
        examples=["+919876543210"],
        description="Customer phone number in E.164 format (required for payment links)",
    )
    customer_email: Optional[str] = Field(
        default=None,
        max_length=128,
        examples=["customer@example.com"],
        description="Customer email address (required for payment links)",
    )
    customer_name: Optional[str] = Field(
        default=None,
        max_length=128,
        examples=["Rohit Sharma"],
        description="Customer full name",
    )


# ─── Response schemas ─────────────────────────────────────────────────────────

class TransactionResponse(BaseModel):
    """Full representation of a Transaction returned by the API."""
    id: int
    razorpay_payment_id: str
    amount: int
    currency: str
    status: TransactionStatus
    failure_reason_code: Optional[str]
    root_cause_category: Optional[RootCauseCategory]
    retry_count: int
    batch_id: Optional[str] = None
    customer_contact: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    total: int
    items: list[TransactionResponse]
