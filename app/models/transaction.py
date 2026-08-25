"""
models/transaction.py — SQLAlchemy ORM model for the Transaction table.
Each row represents one Razorpay payment attempt tracked by the recovery agent.
"""

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TransactionStatus(str, enum.Enum):
    """Lifecycle status of a payment transaction."""
    PENDING = "pending"
    FAILED = "failed"
    RETRY_INITIATED = "retry_initiated"   # order created, awaiting payment confirmation
    LINK_SENT = "link_sent"                # payment link created, awaiting payment confirmation
    RECOVERED = "recovered"              # payment confirmed via webhook or client capture
    ESCALATED = "escalated"              # all recovery attempts exhausted


class RootCauseCategory(str, enum.Enum):
    """Normalised root-cause bucket derived from Razorpay's error_reason field."""
    CARD_DECLINED = "card_declined"
    INSUFFICIENT_FUND = "insufficient_fund"
    GATEWAY_TECHNICAL_ERROR = "gateway_technical_error"
    AUTHENTICATION_FAILED = "authentication_failed"
    SUBSCRIPTION_FAILED = "subscription_failed"   # mandate / recurring payment failure
    UNKNOWN = "unknown"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    razorpay_payment_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Amount in smallest currency unit (paise for INR)",
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), nullable=False, default=TransactionStatus.PENDING
    )
    failure_reason_code: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="Raw error_reason string from Razorpay"
    )
    root_cause_category: Mapped[Optional[RootCauseCategory]] = mapped_column(
        Enum(RootCauseCategory), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of recovery retries attempted"
    )
    batch_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True, comment="Batch identifier to scope transactions by run"
    )
    customer_contact: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="Customer phone number in E.164 format"
    )
    customer_email: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="Customer email address"
    )
    customer_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="Customer full name"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} razorpay_id={self.razorpay_payment_id!r} "
            f"status={self.status} amount={self.amount}>"
        )
