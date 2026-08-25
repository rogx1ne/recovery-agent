"""
routers/webhooks.py — Razorpay webhook receiver.

Closes the recovery loop: when a payment link or retry order is actually paid,
Razorpay fires a webhook here and we mark the transaction as RECOVERED.

Endpoints
---------
POST  /api/v1/webhooks/razorpay     Main Razorpay webhook handler

Setup (Razorpay Dashboard)
--------------------------
1. Go to https://dashboard.razorpay.com/app/webhooks (Test Mode)
2. Add URL: https://your-domain/api/v1/webhooks/razorpay
3. Select events: payment.captured, payment_link.paid
4. Copy the Webhook Secret and add to .env: RAZORPAY_WEBHOOK_SECRET=whsec_xxxx

For local testing use ngrok:
    ngrok http 8000
    # copy the https URL and set it as your webhook URL in dashboard

Signature verification
----------------------
Every webhook is HMAC-SHA256 signed by Razorpay. We verify before processing.
If RAZORPAY_WEBHOOK_SECRET is not set we log a warning but still process the
event — useful for local testing without the full webhook setup.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.audit_log import AuditLog, AuditStep
from app.models.transaction import Transaction, TransactionStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ─── Signature verification ───────────────────────────────────────────────────

def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """
    Verify Razorpay webhook signature.
    Razorpay signs: HMAC-SHA256(body, webhook_secret) → hex digest
    """
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─── Main webhook handler ─────────────────────────────────────────────────────

@router.post(
    "/razorpay",
    summary="Razorpay webhook receiver",
    description=(
        "Receives Razorpay payment events and closes the recovery loop. "
        "When a payment.captured or payment_link.paid event arrives, "
        "the corresponding transaction is marked RECOVERED with a full audit entry."
    ),
    status_code=status.HTTP_200_OK,
)
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_razorpay_signature: str = Header(default="", alias="X-Razorpay-Signature"),
    x_razorpay_event: str = Header(default="", alias="X-Razorpay-Event-Id"),
):
    settings = get_settings()
    body = await request.body()

    # ── Signature verification ─────────────────────────────────────────────
    if settings.razorpay_webhook_secret:
        if not x_razorpay_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-Razorpay-Signature header",
            )
        if not _verify_signature(body, x_razorpay_signature, settings.razorpay_webhook_secret):
            logger.warning("Webhook signature verification FAILED for event %s", x_razorpay_event)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Webhook signature verification failed",
            )
        logger.info("Webhook signature verified OK for event %s", x_razorpay_event)
    else:
        logger.warning(
            "RAZORPAY_WEBHOOK_SECRET not configured — skipping signature verification. "
            "Set it in .env for production use."
        )

    # ── Parse event ────────────────────────────────────────────────────────
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON in webhook body",
        )

    event_type = payload.get("event", "")
    logger.info("Received Razorpay webhook: %s", event_type)

    # ── Route to handler ───────────────────────────────────────────────────
    if event_type == "payment.captured":
        return _handle_payment_captured(payload, db)

    if event_type == "payment_link.paid":
        return _handle_payment_link_paid(payload, db)

    # Acknowledge unhandled events gracefully (Razorpay expects 200)
    logger.debug("Unhandled webhook event type: %s — acknowledged", event_type)
    return {"acknowledged": True, "event": event_type, "action": "ignored"}


# ─── Event handlers ───────────────────────────────────────────────────────────

def _handle_payment_captured(payload: dict, db: Session) -> dict:
    """
    Handle payment.captured — a retry order was successfully paid.

    We look up the transaction by the payment ID embedded in the event notes
    (we set notes.original_payment_id when creating retry orders).
    """
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    captured_payment_id = payment.get("id", "")
    notes = payment.get("notes", {})
    original_payment_id = notes.get("original_payment_id", "")

    # Try to find the transaction by original payment ID (set in retry notes)
    tx = None
    if original_payment_id:
        tx = (
            db.query(Transaction)
            .filter(Transaction.razorpay_payment_id == original_payment_id)
            .first()
        )
    # Fallback: look up by the captured payment ID itself
    if not tx and captured_payment_id:
        tx = (
            db.query(Transaction)
            .filter(Transaction.razorpay_payment_id == captured_payment_id)
            .first()
        )

    if not tx:
        logger.warning(
            "payment.captured: could not find transaction for payment_id=%s original=%s",
            captured_payment_id,
            original_payment_id,
        )
        return {"acknowledged": True, "event": "payment.captured", "action": "no_match"}

    return _mark_recovered(
        db, tx,
        detail=f"payment.captured webhook received for {captured_payment_id}.",
        reasoning=(
            f"Razorpay confirmed payment {captured_payment_id} was successfully captured. "
            f"This was a retry attempt for original failed payment {original_payment_id}. "
            "Transaction marked recovered based on authoritative Razorpay confirmation."
        ),
    )


def _handle_payment_link_paid(payload: dict, db: Session) -> dict:
    """
    Handle payment_link.paid — a recovery payment link was paid by the customer.

    The link's reference_id was set to 'recovery_<original_payment_id>' when created.
    """
    link = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    link_id = link.get("id", "")
    reference_id = link.get("reference_id", "")     # 'recovery_pay_XXXXX'
    paid_amount = link.get("amount_paid", 0)

    # Extract original payment ID from reference_id (supports recovery_ and rec_ prefixes)
    original_payment_id = ""
    if reference_id:
        if reference_id.startswith("recovery_"):
            original_payment_id = reference_id[len("recovery_"):]
        elif reference_id.startswith("rec_"):
            original_payment_id = reference_id[len("rec_"):]
        else:
            original_payment_id = reference_id

    tx = None
    if original_payment_id:
        tx = (
            db.query(Transaction)
            .filter(
                (Transaction.razorpay_payment_id == original_payment_id)
                | (Transaction.razorpay_payment_id.startswith(original_payment_id))
            )
            .first()
        )

    if not tx:
        logger.warning(
            "payment_link.paid: could not find transaction for reference_id=%s link_id=%s",
            reference_id,
            link_id,
        )
        return {"acknowledged": True, "event": "payment_link.paid", "action": "no_match"}

    return _mark_recovered(
        db, tx,
        detail=(
            f"payment_link.paid webhook received. Link {link_id} was paid. "
            f"Amount recovered: ₹{paid_amount / 100:.2f}."
        ),
        reasoning=(
            f"Customer completed payment via recovery link {link_id} "
            f"(reference: {reference_id}). "
            "The payment link was created as a recovery fallback after the original "
            f"payment {original_payment_id} failed. Marking as recovered based on "
            "Razorpay webhook confirmation."
        ),
    )


def _mark_recovered(db: Session, tx: Transaction, detail: str, reasoning: str) -> dict:
    """Mark a transaction RECOVERED and write the OUTCOME audit log."""
    if tx.status == TransactionStatus.RECOVERED:
        logger.info("Transaction %d already RECOVERED — skipping duplicate webhook", tx.id)
        return {"acknowledged": True, "action": "already_recovered", "transaction_id": tx.id}

    from datetime import datetime, timezone
    tx.status = TransactionStatus.RECOVERED
    tx.updated_at = datetime.now(timezone.utc)

    log = AuditLog(
        transaction_id=tx.id,
        step=AuditStep.OUTCOME,
        detail=detail,
        reasoning=reasoning,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()
    db.refresh(tx)

    logger.info("Transaction %d marked RECOVERED via webhook", tx.id)
    return {
        "acknowledged": True,
        "action": "marked_recovered",
        "transaction_id": tx.id,
        "razorpay_payment_id": tx.razorpay_payment_id,
        "amount_inr": tx.amount / 100,
    }
