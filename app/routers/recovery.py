"""
routers/recovery.py — Endpoint to trigger the recovery pipeline for a
specific failed transaction.

Endpoints
---------
POST   /api/v1/recovery/{transaction_id}    Run the full recovery pipeline
GET    /api/v1/recovery/{transaction_id}/status   Check current recovery state
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.transaction import Transaction, TransactionStatus
from app.services.executor import run_recovery

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recovery", tags=["Recovery"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post(
    "/{transaction_id}",
    summary="Trigger recovery pipeline",
    description=(
        "Run the full recovery pipeline (detect → classify → decide → execute → outcome) "
        "for a failed transaction. Writes an AuditLog row at each stage. "
        "Returns a summary of every step taken and any Razorpay artefacts created "
        "(order_id, payment_link_url)."
    ),
    responses={
        200: {"description": "Pipeline completed (check final_status for result)"},
        404: {"description": "Transaction not found"},
        409: {"description": "Transaction is not in a recoverable state"},
        500: {"description": "Recovery pipeline raised an unexpected error"},
    },
)
def trigger_recovery(transaction_id: int, db: DbDep):
    tx: Transaction | None = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found.",
        )

    if tx.status not in (TransactionStatus.FAILED, TransactionStatus.PENDING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Transaction {transaction_id} has status '{tx.status.value}' "
                "and does not need recovery. Only 'failed' or 'pending' transactions "
                "can be processed."
            ),
        )

    try:
        result = run_recovery(transaction_id=transaction_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        logger.error("Recovery pipeline error for tx %d: %s", transaction_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return result


@router.get(
    "/{transaction_id}/status",
    summary="Check recovery status",
    description="Return the current status and retry count for a transaction.",
)
def recovery_status(transaction_id: int, db: DbDep):
    tx: Transaction | None = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found.",
        )
    return {
        "transaction_id": tx.id,
        "razorpay_payment_id": tx.razorpay_payment_id,
        "status": tx.status,
        "root_cause_category": tx.root_cause_category,
        "retry_count": tx.retry_count,
        "failure_reason_code": tx.failure_reason_code,
        "updated_at": tx.updated_at,
    }
