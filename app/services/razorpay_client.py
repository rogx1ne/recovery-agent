"""
services/razorpay_client.py — Thin wrapper around the Razorpay Python SDK.

All interactions with Razorpay (fetching payments, creating payment links,
capturing payments) go through this module so the rest of the codebase
never imports `razorpay` directly.

NOTE: This uses test-mode credentials from .env.  In test mode:
  - No real money moves.
  - Certain magic payment IDs/cards trigger specific failure codes.
  - Payment links can be created and inspected on the dashboard.

Stubs for create_payment_link and re-attempt are clearly marked so they
can be wired to real Razorpay APIs when needed.
"""

import logging
from typing import Any

import razorpay  # type: ignore[import-untyped]

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _build_client() -> razorpay.Client:
    """Instantiate a Razorpay client with test credentials from config."""
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


# Module-level singleton — safe because credentials are read-only at startup
_client: razorpay.Client = _build_client()


# ─── Payment fetching ─────────────────────────────────────────────────────────

def fetch_payment(payment_id: str) -> dict[str, Any]:
    """
    Fetch full payment details from Razorpay.

    Returns the raw Razorpay payment object dict.
    Raises razorpay.errors.BadRequestError if the ID is unknown.
    """
    logger.info("Fetching payment %s from Razorpay", payment_id)
    try:
        payment = _client.payment.fetch(payment_id)
        return payment
    except Exception as exc:
        logger.error("Failed to fetch payment %s: %s", payment_id, exc)
        raise


def fetch_payment_error_details(payment_id: str) -> dict[str, Any]:
    """
    Extract the error block from a failed payment.

    Razorpay embeds error details in the payment object itself under
    'error_code', 'error_description', 'error_source', 'error_step',
    'error_reason' — this helper pulls them out as a flat dict.
    """
    payment = fetch_payment(payment_id)
    return {
        "error_code": payment.get("error_code", ""),
        "error_description": payment.get("error_description", ""),
        "error_source": payment.get("error_source", ""),
        "error_step": payment.get("error_step", ""),
        "error_reason": payment.get("error_reason", ""),
        "status": payment.get("status", ""),
        "amount": payment.get("amount", 0),
        "currency": payment.get("currency", "INR"),
    }


# ─── Payment capture ──────────────────────────────────────────────────────────

def capture_payment(payment_id: str, amount: int, currency: str = "INR") -> dict[str, Any]:
    """
    Capture an authorized payment.

    In test mode this will work for payments that are in 'authorized' state.
    """
    logger.info("Capturing payment %s for amount %d %s", payment_id, amount, currency)
    try:
        result = _client.payment.capture(payment_id, amount, {"currency": currency})
        return result
    except Exception as exc:
        logger.error("Capture failed for %s: %s", payment_id, exc)
        raise


def _extract_razorpay_error(exc: Exception) -> str:
    """
    Extract full, human-readable error detail from a Razorpay SDK exception.
    Captures class name, code, description, and reason.
    """
    err_type = type(exc).__name__
    err_msg = str(exc).strip()

    # Check if there's structured data in args
    if hasattr(exc, "args") and exc.args and isinstance(exc.args[0], dict):
        d = exc.args[0]
        code = d.get("code") or d.get("error", {}).get("code", "")
        desc = d.get("description") or d.get("error", {}).get("description", "")
        reason = d.get("reason") or d.get("error", {}).get("reason", "")
        field = d.get("field") or d.get("error", {}).get("field", "")
        parts = [str(p) for p in [code, desc, field, reason] if p]
        if parts:
            return f"[{err_type}] {' | '.join(parts)}"

    if err_msg:
        return f"[{err_type}] {err_msg}"

    return f"[{err_type}] Unknown error"


# ─── Payment link ─────────────────────────────────────────────────────────────

def create_payment_link(
    amount: int,
    currency: str,
    description: str,
    customer_contact: str,
    customer_email: str,
    customer_name: str = "Customer",
    reference_id: str | None = None,
    expire_minutes: int | None = None,
) -> dict[str, Any]:
    """
    Create a Razorpay Payment Link and return the link object.

    customer_contact and customer_email are required parameters. If either is missing,
    callers must not attempt link creation and must escalate cleanly.

    Docs: https://razorpay.com/docs/api/payment-links/

    Returns dict with at minimum:
        {
            "id": "plink_XXXXXXXXXXXX",
            "short_url": "https://rzp.io/i/XXXXX",
            "status": "created",
        }
    """
    if not customer_contact or not customer_email:
        raise ValueError("Both customer_contact and customer_email are required to create a payment link.")
    settings_ = get_settings()
    expire_by = None
    if expire_minutes is not None:
        import time
        expire_by = int(time.time()) + (expire_minutes * 60)

    payload: dict[str, Any] = {
        "amount": amount,
        "currency": currency,
        "description": description,
        "customer": {
            "name": customer_name,
            "email": customer_email,
            "contact": customer_contact,
        },
        "notify": {
            "sms": False,
            "email": False,
        },
        "reminder_enable": False,
        "callback_url": settings_.callback_url,
        "callback_method": "get",
    }
    if reference_id:
        payload["reference_id"] = reference_id
    if expire_by:
        payload["expire_by"] = expire_by

    logger.info("Creating payment link for amount %d %s", amount, currency)
    try:
        result = _client.payment_link.create(payload)
        logger.info("Payment link created: %s", result.get("id"))
        return result
    except Exception as exc:
        err_detail = _extract_razorpay_error(exc)
        logger.error("Failed to create payment link: %s", err_detail)
        raise RuntimeError(f"Razorpay payment link creation failed: {err_detail}") from exc


# ─── Re-attempt payment (STUB) ────────────────────────────────────────────────

def create_order_for_retry(
    amount: int,
    currency: str = "INR",
    receipt: str | None = None,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Create a new Razorpay Order for a retry attempt.

    An Order is the correct mechanism to re-initiate a payment — you can't
    "retry" a failed payment_id directly via the API.  The frontend (when
    built) would use this order_id to open Razorpay Checkout.

    Returns the Razorpay Order object dict.
    """
    payload: dict[str, Any] = {
        "amount": amount,
        "currency": currency,
        "payment_capture": 1,
    }
    if receipt:
        payload["receipt"] = receipt
    if notes:
        payload["notes"] = notes

    logger.info("Creating retry order for amount %d %s", amount, currency)
    try:
        result = _client.order.create(payload)
        logger.info("Retry order created: %s", result.get("id"))
        return result
    except Exception as exc:
        err_detail = _extract_razorpay_error(exc)
        logger.error("Failed to create retry order: %s", err_detail)
        raise RuntimeError(f"Razorpay retry order creation failed: {err_detail}") from exc
