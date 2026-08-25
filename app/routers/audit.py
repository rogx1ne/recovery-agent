"""
routers/audit.py — Endpoints to read the audit trail.

Endpoints
---------
GET   /api/v1/audit/                              All audit logs (paginated)
GET   /api/v1/audit/transaction/{transaction_id}  All logs for one transaction
GET   /api/v1/audit/{log_id}                      A single audit log entry
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.audit_log import AuditLog, AuditStep
from app.schemas.audit_log import AuditLogListResponse, AuditLogResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", tags=["Audit Trail"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get(
    "/",
    response_model=AuditLogListResponse,
    summary="List all audit log entries",
    description="Paginated list of all audit log entries across all transactions.",
)
def list_audit_logs(
    db: DbDep,
    step_filter: Optional[AuditStep] = Query(
        default=None, alias="step", description="Filter by pipeline step"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = db.query(AuditLog)
    if step_filter:
        q = q.filter(AuditLog.step == step_filter)
    total = q.count()
    items = q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return AuditLogListResponse(total=total, items=items)


@router.get(
    "/transaction/{transaction_id}",
    response_model=AuditLogListResponse,
    summary="Audit trail for one transaction",
    description=(
        "Returns all audit log entries for a specific transaction, "
        "ordered chronologically. This is the primary way to inspect "
        "why each decision was made."
    ),
)
def list_transaction_audit_logs(transaction_id: int, db: DbDep):
    items = (
        db.query(AuditLog)
        .filter(AuditLog.transaction_id == transaction_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )
    return AuditLogListResponse(total=len(items), items=items)


@router.get(
    "/{log_id}",
    response_model=AuditLogResponse,
    summary="Get a single audit log entry",
)
def get_audit_log(log_id: int, db: DbDep):
    log = db.get(AuditLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"AuditLog {log_id} not found")
    return log
