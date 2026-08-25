"""
routers/transactions.py — CRUD endpoints for Transaction records.

Endpoints
---------
POST   /api/v1/transactions/              Create a new transaction record
GET    /api/v1/transactions/              List all transactions (with optional status filter)
GET    /api/v1/transactions/{id}          Get a single transaction by ID
GET    /api/v1/transactions/callback      Razorpay payment link callback (stub)
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.transaction import Transaction, TransactionStatus
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transactions", tags=["Transactions"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post(
    "/",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a transaction",
    description=(
        "Create a new transaction record. Use this to register a Razorpay payment "
        "(typically a failed one) before running the recovery pipeline."
    ),
)
def create_transaction(payload: TransactionCreate, db: DbDep):
    # Guard against duplicate razorpay_payment_id
    existing = (
        db.query(Transaction)
        .filter(Transaction.razorpay_payment_id == payload.razorpay_payment_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transaction with razorpay_payment_id='{payload.razorpay_payment_id}' already exists (id={existing.id}).",
        )

    tx = Transaction(
        razorpay_payment_id=payload.razorpay_payment_id,
        amount=payload.amount,
        currency=payload.currency,
        status=payload.status,
        failure_reason_code=payload.failure_reason_code,
        batch_id=payload.batch_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    logger.info("Created transaction id=%d rzp_id=%s batch_id=%s", tx.id, tx.razorpay_payment_id, tx.batch_id)
    return tx


@router.get(
    "/",
    response_model=TransactionListResponse,
    summary="List transactions",
    description="List all tracked transactions, optionally filtered by status or batch ID.",
)
def list_transactions(
    db: DbDep,
    status_filter: Optional[TransactionStatus] = Query(
        default=None, alias="status", description="Filter by transaction status"
    ),
    batch_id: Optional[str] = Query(
        default=None, description="Filter by batch ID"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = db.query(Transaction)
    if status_filter:
        q = q.filter(Transaction.status == status_filter)
    if batch_id:
        q = q.filter(Transaction.batch_id == batch_id)
    total = q.count()
    items = q.order_by(Transaction.id.desc()).offset(offset).limit(limit).all()
    return TransactionListResponse(total=total, items=items)


@router.get(
    "/callback",
    summary="Payment link callback (stub)",
    description=(
        "Stub endpoint that Razorpay redirects to after a payment link is paid. "
        "In production this would verify the payment signature and update the record."
    ),
)
def payment_link_callback(
    razorpay_payment_id: Optional[str] = Query(default=None),
    razorpay_payment_link_id: Optional[str] = Query(default=None),
    razorpay_payment_link_reference_id: Optional[str] = Query(default=None),
    razorpay_payment_link_status: Optional[str] = Query(default=None),
    razorpay_signature: Optional[str] = Query(default=None),
):
    """
    Razorpay appends query params when redirecting after link payment.
    This stub logs them and returns a success message.
    In production: verify the signature using razorpay.utility.verify_payment_link_signature.
    """
    logger.info(
        "Payment link callback received: payment_id=%s link_id=%s status=%s",
        razorpay_payment_id,
        razorpay_payment_link_id,
        razorpay_payment_link_status,
    )
    return {
        "message": "Callback received (stub — signature not verified in test mode)",
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_payment_link_id": razorpay_payment_link_id,
        "razorpay_payment_link_status": razorpay_payment_link_status,
    }


@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse,
    summary="Get a transaction",
)
def get_transaction(transaction_id: int, db: DbDep):
    tx = db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
    return tx
