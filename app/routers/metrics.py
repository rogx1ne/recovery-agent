"""
routers/metrics.py — Batch summary metrics endpoint.

Endpoints
---------
GET   /api/v1/metrics/summary      Overall recovery stats across all transactions
GET   /api/v1/metrics/by-category  Recovery rate broken down by root-cause category
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.transaction import RootCauseCategory, Transaction, TransactionStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stats", tags=["Stats"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get(
    "/summary",
    summary="Overall recovery summary",
    description=(
        "Returns high-level batch statistics: total transactions, counts by status, "
        "overall recovery rate (%), and total amount recovered (in smallest unit)."
    ),
)
def get_summary(db: DbDep):
    total = db.query(func.count(Transaction.id)).scalar() or 0

    status_counts: dict[str, int] = {}
    for row in db.query(Transaction.status, func.count(Transaction.id)).group_by(Transaction.status).all():
        status_counts[row[0].value] = row[1]

    recovered_count = status_counts.get(TransactionStatus.RECOVERED.value, 0)
    failed_count = status_counts.get(TransactionStatus.FAILED.value, 0)
    escalated_count = status_counts.get(TransactionStatus.ESCALATED.value, 0)
    pending_count = status_counts.get(TransactionStatus.PENDING.value, 0)

    # Amount recovered = sum of amounts for RECOVERED transactions
    amount_recovered = (
        db.query(func.sum(Transaction.amount))
        .filter(Transaction.status == TransactionStatus.RECOVERED)
        .scalar()
        or 0
    )

    attempted = recovered_count + escalated_count  # transactions that went through the pipeline
    recovery_rate_pct = (recovered_count / attempted * 100) if attempted > 0 else 0.0

    return {
        "total_transactions": total,
        "by_status": {
            "pending": pending_count,
            "failed": failed_count,
            "recovered": recovered_count,
            "escalated": escalated_count,
        },
        "recovery_rate_pct": round(recovery_rate_pct, 2),
        "amount_recovered_paise": amount_recovered,
        "amount_recovered_inr": round(amount_recovered / 100, 2),
        "pipeline_attempted": attempted,
    }


@router.get(
    "/by-category",
    summary="Recovery breakdown by root-cause category",
    description=(
        "Shows recovery rate and counts per root-cause category. "
        "Useful for identifying which failure types are hardest to recover."
    ),
)
def get_by_category(db: DbDep):
    rows = (
        db.query(
            Transaction.root_cause_category,
            Transaction.status,
            func.count(Transaction.id).label("count"),
            func.sum(Transaction.amount).label("total_amount"),
        )
        .group_by(Transaction.root_cause_category, Transaction.status)
        .all()
    )

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
        attempted = recovered + escalated
        data["recovery_rate_pct"] = round((recovered / attempted * 100) if attempted > 0 else 0.0, 2)

    return {"categories": summary}
