"""
schemas/audit_log.py — Pydantic v2 schemas for AuditLog API endpoints.
"""

from datetime import datetime

from pydantic import BaseModel

from app.models.audit_log import AuditStep


class AuditLogResponse(BaseModel):
    """Full representation of an AuditLog entry returned by the API."""
    id: int
    transaction_id: int
    step: AuditStep
    detail: str
    reasoning: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    total: int
    items: list[AuditLogResponse]
