"""
models/audit_log.py — SQLAlchemy ORM model for the AuditLog table.
Every decision in the recovery pipeline writes a row here with a human-readable
'reasoning' field so the audit trail is inspectable without touching code.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AuditStep(str, enum.Enum):
    """Ordered steps in the recovery pipeline."""
    DETECTED = "detected"       # payment failure was identified
    CLASSIFIED = "classified"   # root-cause category was determined
    DECIDED = "decided"         # recovery action was chosen by policy
    EXECUTED = "executed"       # action was attempted via Razorpay API
    OUTCOME = "outcome"         # final result (recovered / escalated)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transaction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.id"), nullable=False, index=True
    )
    step: Mapped[AuditStep] = mapped_column(
        Enum(AuditStep),
        nullable=False,
        comment="Which pipeline stage produced this log entry",
    )
    detail: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Factual description of what happened at this step",
    )
    reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Why this decision/action was chosen — inspectable rationale",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship — useful for joins but not strictly required for the API
    transaction: Mapped["Transaction"] = relationship(  # noqa: F821
        "Transaction", backref="audit_logs", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} tx_id={self.transaction_id} "
            f"step={self.step} ts={self.timestamp.isoformat()}>"
        )
