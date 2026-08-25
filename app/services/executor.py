"""
services/executor.py — Orchestrates the full recovery pipeline for a single
failed transaction and writes an AuditLog entry at every step.

Pipeline stages
---------------
1. DETECTED  — read the failure from the DB (already recorded by the router)
2. CLASSIFIED — call classifier to get RootCauseCategory
3. DECIDED   — look up RecoveryPolicy from the policy table
4. EXECUTED  — call Razorpay API to perform the chosen action
5. OUTCOME   — record the final result (recovered / escalated)

All Razorpay API calls are wrapped in try/except; failures are recorded in
the audit log and the transaction is escalated rather than left in limbo.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.audit_log import AuditLog, AuditStep
from app.models.transaction import RootCauseCategory, Transaction, TransactionStatus
from app.services import classifier as clf
from app.services import razorpay_client as rzp
from app.services.decision_policy import (
    RecoveryAction,
    RecoveryPolicy,
    get_policy,
    should_retry,
    should_send_link_after_retries,
)

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _write_audit(
    db: Session,
    transaction_id: int,
    step: AuditStep,
    detail: str,
    reasoning: str,
) -> AuditLog:
    """Persist a single AuditLog row and flush (does not commit — caller commits)."""
    log = AuditLog(
        transaction_id=transaction_id,
        step=step,
        detail=detail,
        reasoning=reasoning,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(log)
    db.flush()  # get the id without a full commit
    logger.debug("AuditLog [%s] tx=%d: %s", step, transaction_id, detail)
    return log


def _update_transaction(db: Session, tx: Transaction, **kwargs) -> None:
    """Apply keyword-arg updates to a Transaction and flush."""
    for key, value in kwargs.items():
        setattr(tx, key, value)
    tx.updated_at = datetime.now(timezone.utc)
    db.flush()


# ─── Public entry point ───────────────────────────────────────────────────────

def run_recovery(transaction_id: int, db: Session) -> dict:
    """
    Execute the full recovery pipeline for a transaction.

    Parameters
    ----------
    transaction_id : int
        Primary key of the Transaction row to recover.
    db : Session
        Active SQLAlchemy session (the router passes this via dependency injection).

    Returns
    -------
    dict
        A summary dict with final status, steps taken, and any Razorpay artefacts
        created (order_id, payment_link_url).
    """
    # ── Load transaction ──────────────────────────────────────────────────────
    tx: Transaction | None = db.get(Transaction, transaction_id)
    if tx is None:
        raise ValueError(f"Transaction {transaction_id} not found")

    if tx.status not in (TransactionStatus.FAILED, TransactionStatus.PENDING):
        return {
            "transaction_id": transaction_id,
            "status": tx.status,
            "message": f"Transaction is already in state '{tx.status}' — no recovery needed.",
            "steps": [],
        }

    steps_taken: list[str] = []
    result_artefacts: dict = {}

    try:
        # ── STEP 1: DETECTED ─────────────────────────────────────────────────
        _write_audit(
            db, tx.id, AuditStep.DETECTED,
            detail=(
                f"Transaction {tx.razorpay_payment_id} detected as failed. "
                f"Raw failure_reason_code: '{tx.failure_reason_code}'. "
                f"Amount: {tx.amount} {tx.currency}."
            ),
            reasoning=(
                "Recovery pipeline initiated because transaction status is 'failed'. "
                "The failure_reason_code was recorded at payment creation time."
            ),
        )
        steps_taken.append("detected")

        # ── STEP 2: CLASSIFIED ───────────────────────────────────────────────
        settings = get_settings()
        if settings.use_llm_classifier:
            from app.services.llm_classifier import classify_with_llm
            category, classification_reasoning, used_ai = classify_with_llm(
                error_reason=tx.failure_reason_code,
                amount=tx.amount,
                currency=tx.currency,
            )
        else:
            category = clf.classify(tx.failure_reason_code)
            classification_reasoning = clf.explain_classification(
                tx.failure_reason_code, category
            )
            classification_reasoning = f"[Rules-based classifier] {classification_reasoning}"
            used_ai = False

        _update_transaction(db, tx, root_cause_category=category)
        _write_audit(
            db, tx.id, AuditStep.CLASSIFIED,
            detail=(
                f"Root cause classified as '{category.value}' "
                f"({'AI' if used_ai else 'rules-based'} classifier)."
            ),
            reasoning=classification_reasoning,
        )
        steps_taken.append("classified")

        # ── STEP 3: DECIDED ──────────────────────────────────────────────────
        from app.services.decision_policy import is_high_value_transaction
        policy: RecoveryPolicy = get_policy(category)
        is_vip = is_high_value_transaction(tx.amount)
        
        decided_reasoning = policy.rationale
        if is_vip:
            decided_reasoning += " [VIP Priority: Transaction amount ≥ ₹10,000. Customer flagged for priority recovery handling.]"

        _write_audit(
            db, tx.id, AuditStep.DECIDED,
            detail=(
                f"Policy selected: action='{policy.action.value}', "
                f"max_retries={policy.max_retries}, "
                f"retry_delay={policy.retry_delay_seconds}s."
                f"{' (VIP High Value)' if is_vip else ''}"
            ),
            reasoning=decided_reasoning,
        )
        steps_taken.append("decided")

        # ── STEP 4: EXECUTED ─────────────────────────────────────────────────
        final_status, exec_detail, exec_reasoning = _execute_policy(
            db, tx, policy, result_artefacts
        )
        steps_taken.append("executed")

        # ── STEP 5: OUTCOME ──────────────────────────────────────────────────
        _update_transaction(db, tx, status=final_status)
        _write_audit(
            db, tx.id, AuditStep.OUTCOME,
            detail=exec_detail,
            reasoning=exec_reasoning,
        )
        steps_taken.append("outcome")

        db.commit()
        db.refresh(tx)

        return {
            "transaction_id": transaction_id,
            "razorpay_payment_id": tx.razorpay_payment_id,
            "final_status": final_status.value,
            "steps_taken": steps_taken,
            "artefacts": result_artefacts,
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Recovery pipeline failed for transaction %d", transaction_id)
        raise RuntimeError(
            f"Recovery pipeline raised an unexpected error: {exc}"
        ) from exc


# ─── Policy execution logic ───────────────────────────────────────────────────

def _execute_policy(
    db: Session,
    tx: Transaction,
    policy: RecoveryPolicy,
    artefacts: dict,
) -> tuple[TransactionStatus, str, str]:
    """
    Dispatch to the correct execution branch based on policy.action.

    Returns (final_status, outcome_detail, outcome_reasoning).
    """
    if policy.action == RecoveryAction.IMMEDIATE_RETRY:
        return _handle_immediate_retry(db, tx, policy, artefacts)

    if policy.action == RecoveryAction.RETRY_THEN_LINK:
        return _handle_retry_then_link(db, tx, policy, artefacts)

    if policy.action == RecoveryAction.PAYMENT_LINK:
        return _handle_payment_link(tx, policy, artefacts)

    # ESCALATE (or unknown action)
    return (
        TransactionStatus.ESCALATED,
        "Policy dictates escalation. No automated action taken.",
        "The assigned policy action is ESCALATE — this requires manual review.",
    )


def _attempt_retry(tx: Transaction, db: Session, policy: RecoveryPolicy) -> dict | None:
    """
    Attempt one Razorpay retry by creating a new order.

    Increments tx.retry_count.  Returns the order dict on success, None on failure.
    Writes an EXECUTED audit row for each attempt.
    """
    if policy.retry_delay_seconds > 0:
        logger.info(
            "Waiting %ds before retry for tx %d", policy.retry_delay_seconds, tx.id
        )
        time.sleep(policy.retry_delay_seconds)

    attempt_num = tx.retry_count + 1
    logger.info("Retry attempt %d for tx %d", attempt_num, tx.id)

    try:
        order = rzp.create_order_for_retry(
            amount=tx.amount,
            currency=tx.currency,
            receipt=f"retry_{tx.razorpay_payment_id}_{attempt_num}",
            notes={"original_payment_id": tx.razorpay_payment_id, "attempt": str(attempt_num)},
        )
        _update_transaction(db, tx, retry_count=tx.retry_count + 1)
        _write_audit(
            db, tx.id, AuditStep.EXECUTED,
            detail=(
                f"Retry attempt {attempt_num}: created Razorpay order "
                f"'{order.get('id', 'N/A')}' for amount {tx.amount} {tx.currency}."
            ),
            reasoning=(
                f"Retry #{attempt_num} initiated as per policy. "
                f"A new Razorpay order is required to re-initiate checkout."
            ),
        )
        return order
    except Exception as exc:
        _update_transaction(db, tx, retry_count=tx.retry_count + 1)
        _write_audit(
            db, tx.id, AuditStep.EXECUTED,
            detail=f"Retry attempt {attempt_num} failed with error: {exc}",
            reasoning=(
                f"Razorpay order creation for retry #{attempt_num} raised an exception. "
                "Recording the failure and proceeding with escalation logic."
            ),
        )
        logger.warning("Retry %d failed for tx %d: %s", attempt_num, tx.id, exc)
        return None


def _handle_immediate_retry(
    db: Session, tx: Transaction, policy: RecoveryPolicy, artefacts: dict
) -> tuple[TransactionStatus, str, str]:
    """
    Try up to policy.max_retries times. Escalate if all fail.
    """
    last_order = None
    while should_retry(policy, tx.retry_count):
        last_order = _attempt_retry(tx, db, policy)
        if last_order:
            artefacts["retry_order_id"] = last_order.get("id")
            return (
                TransactionStatus.RETRY_INITIATED,
                f"Recovery initiated via Razorpay order {last_order.get('id')}. "
                f"Total retries: {tx.retry_count}. Awaiting payment confirmation.",
                "Razorpay order created successfully. The customer's frontend can "
                "use this order to complete checkout. Recovery initiated, awaiting payment confirmation.",
            )

    # All retries exhausted
    return (
        TransactionStatus.ESCALATED,
        f"All {policy.max_retries} retry attempts exhausted. Escalating for manual review.",
        "Each retry attempt resulted in a Razorpay API error. "
        "No further automated action is possible — escalation is required.",
    )


def _handle_retry_then_link(
    db: Session, tx: Transaction, policy: RecoveryPolicy, artefacts: dict
) -> tuple[TransactionStatus, str, str]:
    """
    Try once; if it succeeds, set status to retry_initiated. If it fails (or retries exhausted),
    fall back to a payment link.
    """
    if should_retry(policy, tx.retry_count):
        order = _attempt_retry(tx, db, policy)
        if order:
            artefacts["retry_order_id"] = order.get("id")
            return (
                TransactionStatus.RETRY_INITIATED,
                f"Retry order {order.get('id')} created. Recovery initiated, awaiting payment confirmation.",
                "First retry attempt created Razorpay order. Recovery initiated, awaiting payment confirmation.",
            )
        # Retry failed — fall through to payment link

    # Either retry failed or retries already exhausted → send payment link
    return _handle_payment_link(tx, policy, artefacts)


def _handle_payment_link(
    tx: Transaction, policy: RecoveryPolicy, artefacts: dict
) -> tuple[TransactionStatus, str, str]:
    """
    Create a Razorpay payment link and mark as link_sent (awaiting payment confirmation).
    """
    from app.config import get_settings
    from app.services.llm_classifier import generate_recovery_message
    settings = get_settings()

    try:
        link = rzp.create_payment_link(
            amount=tx.amount,
            currency=tx.currency,
            description=f"Payment recovery for {tx.razorpay_payment_id}",
            reference_id=f"recovery_{tx.razorpay_payment_id}",
            expire_minutes=settings.payment_link_expire_minutes,
        )
        short_url = link.get("short_url", "N/A")
        link_id = link.get("id", "N/A")
        artefacts["payment_link_id"] = link_id
        artefacts["payment_link_url"] = short_url

        # Generate conversational Hinglish recovery message (WhatsApp ready)
        category = tx.root_cause_category or RootCauseCategory.UNKNOWN
        msg = generate_recovery_message(
            error_reason=tx.failure_reason_code,
            amount=tx.amount,
            currency=tx.currency,
            category=category,
            link_url=short_url,
        )
        artefacts["recovery_message"] = msg

        return (
            TransactionStatus.LINK_SENT,
            f"Payment link created: {short_url} (link id: {link_id}). "
            f"Expires in {settings.payment_link_expire_minutes} minutes.",
            (
                "A Razorpay payment link was generated alongside an AI-crafted Hinglish recovery "
                "message ready for WhatsApp/SMS dispatch. Link sent, awaiting payment confirmation."
            ),
        )
    except Exception as exc:
        artefacts["payment_link_error"] = str(exc)
        return (
            TransactionStatus.ESCALATED,
            f"Payment link creation failed: {exc}. Escalating.",
            (
                "Razorpay payment link API returned an error. "
                "Cannot complete automated recovery — escalating for manual intervention."
            ),
        )
