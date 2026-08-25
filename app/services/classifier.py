"""
services/classifier.py — Maps Razorpay's raw error_reason string to a
normalised RootCauseCategory enum value.

Design rationale
----------------
Razorpay returns an `error_reason` field on failed payments.  The values
are NOT guaranteed to be an exhaustive closed set across all gateway
integrations, so the classifier uses a priority-ordered substring/exact
lookup table and falls back to UNKNOWN when nothing matches.

This keeps classification logic in one place and completely inspectable —
no ML, no regex soup.
"""

import logging

from app.models.transaction import RootCauseCategory

logger = logging.getLogger(__name__)

# ─── Classification lookup table ─────────────────────────────────────────────
#
# Each entry is (substring_to_match_lowercased, RootCauseCategory).
# The table is checked top-to-bottom; first match wins.
# Add new Razorpay error_reason values here as you encounter them.
#
_REASON_MAP: list[tuple[str, RootCauseCategory]] = [
    # Insufficient funds / credit limit
    ("insufficient_funds", RootCauseCategory.INSUFFICIENT_FUND),
    ("insufficient fund", RootCauseCategory.INSUFFICIENT_FUND),
    ("low balance", RootCauseCategory.INSUFFICIENT_FUND),
    ("credit_limit", RootCauseCategory.INSUFFICIENT_FUND),

    # Card declined by issuer (catch-all decline — must come after more specific ones)
    ("card_declined", RootCauseCategory.CARD_DECLINED),
    ("card declined", RootCauseCategory.CARD_DECLINED),
    ("do_not_honour", RootCauseCategory.CARD_DECLINED),
    ("do not honour", RootCauseCategory.CARD_DECLINED),
    ("restricted_card", RootCauseCategory.CARD_DECLINED),
    ("blocked", RootCauseCategory.CARD_DECLINED),

    # Authentication / 3-D Secure failures
    ("authentication_failed", RootCauseCategory.AUTHENTICATION_FAILED),
    ("authentication failed", RootCauseCategory.AUTHENTICATION_FAILED),
    ("invalid_otp", RootCauseCategory.AUTHENTICATION_FAILED),
    ("otp", RootCauseCategory.AUTHENTICATION_FAILED),
    ("3ds", RootCauseCategory.AUTHENTICATION_FAILED),
    ("payment_cancelled", RootCauseCategory.AUTHENTICATION_FAILED),  # user abandoned 3DS

    # Subscription / mandate / recurring payment failures
    ("subscription_failed", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("subscription failed", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("mandate_failed", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("mandate failed", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("emandate", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("nach", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("recurring", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("auto_debit", RootCauseCategory.SUBSCRIPTION_FAILED),
    ("autopay", RootCauseCategory.SUBSCRIPTION_FAILED),

    # Gateway / network technical errors
    ("gateway_technical_error", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
    ("gateway technical error", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
    ("technical_error", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
    ("network_error", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
    ("timeout", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
    ("server_error", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
    ("connection", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
]


def classify(error_reason: str | None) -> RootCauseCategory:
    """
    Given a raw Razorpay error_reason string, return a RootCauseCategory.

    Parameters
    ----------
    error_reason:
        The `error_reason` field from a Razorpay failed payment object.
        May be None or empty if Razorpay did not return one.

    Returns
    -------
    RootCauseCategory
        One of the four known categories, or UNKNOWN if no rule matched.
    """
    if not error_reason:
        logger.warning("No error_reason provided — classifying as UNKNOWN")
        return RootCauseCategory.UNKNOWN

    normalised = error_reason.strip().lower()
    for substring, category in _REASON_MAP:
        if substring in normalised:
            logger.info(
                "Classified %r -> %s (matched rule %r)",
                error_reason,
                category,
                substring,
            )
            return category

    logger.warning("No classification rule matched %r — using UNKNOWN", error_reason)
    return RootCauseCategory.UNKNOWN


def explain_classification(error_reason: str | None, category: RootCauseCategory) -> str:
    """
    Return a human-readable explanation of why a classification was chosen.
    This string is written into AuditLog.reasoning at the CLASSIFIED step.
    """
    if category == RootCauseCategory.UNKNOWN:
        return (
            f"Could not map error_reason={error_reason!r} to any known category. "
            "Falling back to UNKNOWN — manual review recommended."
        )
    return (
        f"error_reason={error_reason!r} matched the lookup table rule for "
        f"'{category.value}'. This category was selected because the raw "
        f"reason string contains a known pattern associated with {category.value} failures."
    )
