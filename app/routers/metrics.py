"""
routers/metrics.py — Batch summary metrics endpoint.

Endpoints
---------
GET   /api/v1/metrics/summary      Overall recovery stats across all transactions
GET   /api/v1/metrics/by-category  Recovery rate broken down by root-cause category
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.transaction import RootCauseCategory, Transaction, TransactionStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stats", tags=["Stats"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get(
    "/batches",
    summary="List available batch IDs",
    description="Returns distinct batch IDs along with transaction count and latest timestamp.",
)
def get_batches(db: DbDep):
    rows = (
        db.query(
            Transaction.batch_id,
            func.count(Transaction.id).label("count"),
            func.max(Transaction.created_at).label("latest_created_at"),
        )
        .filter(Transaction.batch_id.isnot(None))
        .group_by(Transaction.batch_id)
        .order_by(func.max(Transaction.created_at).desc())
        .all()
    )
    return [
        {
            "batch_id": row.batch_id,
            "count": row.count,
            "latest_created_at": row.latest_created_at.isoformat() if row.latest_created_at else None,
        }
        for row in rows
    ]


@router.get(
    "/summary",
    summary="Overall or batch-scoped recovery summary",
    description=(
        "Returns high-level recovery statistics: total transactions, counts by status, "
        "overall recovery rate (%), and total amount recovered. "
        "Optionally scoped to a specific batch_id."
    ),
)
def get_summary(
    db: DbDep,
    batch_id: Optional[str] = Query(
        default=None, description="Optional batch ID to scope metrics to"
    ),
):
    total_q = db.query(func.count(Transaction.id))
    status_q = db.query(Transaction.status, func.count(Transaction.id)).group_by(Transaction.status)
    rec_amount_q = (
        db.query(func.sum(Transaction.amount))
        .filter(Transaction.status == TransactionStatus.RECOVERED)
    )
    pending_amount_q = (
        db.query(func.sum(Transaction.amount))
        .filter(Transaction.status.in_([TransactionStatus.RETRY_INITIATED, TransactionStatus.LINK_SENT]))
    )

    if batch_id:
        total_q = total_q.filter(Transaction.batch_id == batch_id)
        status_q = status_q.filter(Transaction.batch_id == batch_id)
        rec_amount_q = rec_amount_q.filter(Transaction.batch_id == batch_id)
        pending_amount_q = pending_amount_q.filter(Transaction.batch_id == batch_id)

    total = total_q.scalar() or 0

    status_counts: dict[str, int] = {}
    for row in status_q.all():
        status_counts[row[0].value] = row[1]

    recovered_count = status_counts.get(TransactionStatus.RECOVERED.value, 0)
    failed_count = status_counts.get(TransactionStatus.FAILED.value, 0)
    escalated_count = status_counts.get(TransactionStatus.ESCALATED.value, 0)
    pending_count = status_counts.get(TransactionStatus.PENDING.value, 0)
    retry_initiated_count = status_counts.get(TransactionStatus.RETRY_INITIATED.value, 0)
    link_sent_count = status_counts.get(TransactionStatus.LINK_SENT.value, 0)
    pending_confirmation_count = retry_initiated_count + link_sent_count

    # Amount recovered = sum of amounts for RECOVERED transactions ONLY
    amount_recovered = rec_amount_q.scalar() or 0

    # Amount pending confirmation = sum of amounts for RETRY_INITIATED and LINK_SENT
    amount_pending_confirmation = pending_amount_q.scalar() or 0

    attempted = recovered_count + pending_confirmation_count + escalated_count  # transactions that went through pipeline
    recovery_rate_pct = (recovered_count / attempted * 100) if attempted > 0 else 0.0

    return {
        "batch_id": batch_id,
        "total_transactions": total,
        "by_status": {
            "pending": pending_count,
            "failed": failed_count,
            "retry_initiated": retry_initiated_count,
            "link_sent": link_sent_count,
            "pending_confirmation": pending_confirmation_count,
            "recovered": recovered_count,
            "escalated": escalated_count,
        },
        "recovery_rate_pct": round(recovery_rate_pct, 2),
        "amount_recovered_paise": amount_recovered,
        "amount_recovered_inr": round(amount_recovered / 100, 2),
        "amount_pending_confirmation_paise": amount_pending_confirmation,
        "amount_pending_confirmation_inr": round(amount_pending_confirmation / 100, 2),
        "pipeline_attempted": attempted,
    }


@router.get(
    "/by-category",
    summary="Recovery breakdown by root-cause category",
    description=(
        "Shows recovery rate and counts per root-cause category. "
        "Optionally scoped to a specific batch_id."
    ),
)
def get_by_category(
    db: DbDep,
    batch_id: Optional[str] = Query(
        default=None, description="Optional batch ID to scope metrics to"
    ),
):
    query = db.query(
        Transaction.root_cause_category,
        Transaction.status,
        func.count(Transaction.id).label("count"),
        func.sum(Transaction.amount).label("total_amount"),
    )

    if batch_id:
        query = query.filter(Transaction.batch_id == batch_id)

    rows = query.group_by(Transaction.root_cause_category, Transaction.status).all()

    # Build a nested structure: category -> {status -> count}
    summary: dict[str, dict] = {}
    for row in rows:
        cat_key = row.root_cause_category.value if row.root_cause_category else "unclassified"
        status_key = row.status.value

        if cat_key not in summary:
            summary[cat_key] = {"counts": {}, "amount_by_status": {}, "recovery_rate_pct": 0.0}

        summary[cat_key]["counts"][status_key] = row.count
        summary[cat_key]["amount_by_status"][status_key] = row.total_amount or 0

    # Compute per-category recovery rate
    for cat_key, data in summary.items():
        counts = data["counts"]
        recovered = counts.get(TransactionStatus.RECOVERED.value, 0)
        escalated = counts.get(TransactionStatus.ESCALATED.value, 0)
        retry_initiated = counts.get(TransactionStatus.RETRY_INITIATED.value, 0)
        link_sent = counts.get(TransactionStatus.LINK_SENT.value, 0)
        pending_confirmation = retry_initiated + link_sent
        data["pending_confirmation_count"] = pending_confirmation
        attempted = recovered + pending_confirmation + escalated
        data["recovery_rate_pct"] = round((recovered / attempted * 100) if attempted > 0 else 0.0, 2)

    return {"batch_id": batch_id, "categories": summary}
