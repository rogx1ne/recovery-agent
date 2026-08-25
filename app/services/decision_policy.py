"""
services/decision_policy.py — Rules table mapping RootCauseCategory to a
bounded recovery action plan.

Design principles
-----------------
1. Explicit and inspectable: every policy is a named dataclass, not a magic dict.
2. Hard caps: max_retries is finite; the executor must respect it.
3. Documented reasoning: each policy carries a human-readable rationale string
   so AuditLog.reasoning can be populated without any logic elsewhere.

Policy table (matches spec exactly)
------------------------------------
| Category               | Action          | Max retries | Notes                         |
|------------------------|-----------------|-------------|-------------------------------|
| card_declined          | retry_then_link | 1           | retry once, then payment link |
| insufficient_fund      | payment_link    | 0           | no auto-retry                 |
| gateway_technical_error| immediate_retry | 2           | up to 2 immediate retries     |
| authentication_failed  | payment_link    | 0           | no auto-retry                 |
| unknown                | payment_link    | 0           | safe default                  |
"""

from dataclasses import dataclass
from enum import Enum

from app.models.transaction import RootCauseCategory


class RecoveryAction(str, Enum):
    """The set of recovery actions the executor can perform."""
    RETRY_THEN_LINK = "retry_then_link"    # attempt a retry; if retries exhausted, create link
    IMMEDIATE_RETRY = "immediate_retry"    # retry immediately up to max_retries
    PAYMENT_LINK = "payment_link"          # create a payment link, no auto-retry
    ESCALATE = "escalate"                  # no further automated action; manual review


@dataclass(frozen=True)
class RecoveryPolicy:
    """Immutable policy descriptor for a root-cause category."""
    action: RecoveryAction
    max_retries: int
    retry_delay_seconds: int
    rationale: str          # written verbatim into AuditLog.reasoning at DECIDED step


# ─── The authoritative policy table ──────────────────────────────────────────

POLICY_TABLE: dict[RootCauseCategory, RecoveryPolicy] = {
    RootCauseCategory.CARD_DECLINED: RecoveryPolicy(
        action=RecoveryAction.RETRY_THEN_LINK,
        max_retries=1,
        retry_delay_seconds=5,
        rationale=(
            "Card declined by issuer. Policy: attempt one retry after a short delay "
            "to handle transient bank-side rejections. If the retry also fails, "
            "fall back to a payment link so the customer can switch to a different "
            "payment method. No further auto-retries to avoid card lock-out risk."
        ),
    ),
    RootCauseCategory.INSUFFICIENT_FUND: RecoveryPolicy(
        action=RecoveryAction.PAYMENT_LINK,
        max_retries=0,
        retry_delay_seconds=0,
        rationale=(
            "Insufficient funds detected. Policy: do not auto-retry because the "
            "underlying balance issue cannot be resolved by the system. Send a "
            "payment link so the customer can attempt payment at a later time or "
            "with a different funding source."
        ),
    ),
    RootCauseCategory.GATEWAY_TECHNICAL_ERROR: RecoveryPolicy(
        action=RecoveryAction.IMMEDIATE_RETRY,
        max_retries=2,
        retry_delay_seconds=2,
        rationale=(
            "Gateway technical error — likely a transient infrastructure issue. "
            "Policy: retry immediately up to 2 times with a brief pause between "
            "attempts. If both retries fail, escalate for manual review rather "
            "than creating a link (gateway errors may persist for minutes)."
        ),
    ),
    RootCauseCategory.AUTHENTICATION_FAILED: RecoveryPolicy(
        action=RecoveryAction.PAYMENT_LINK,
        max_retries=0,
        retry_delay_seconds=0,
        rationale=(
            "Authentication failed (3DS/OTP). Policy: do not auto-retry — repeated "
            "auto-retries on auth failures can trigger fraud detection on the bank side. "
            "Send a payment link with clear instructions so the customer can complete "
            "authentication manually at their own pace."
        ),
    ),
    RootCauseCategory.SUBSCRIPTION_FAILED: RecoveryPolicy(
        action=RecoveryAction.IMMEDIATE_RETRY,
        max_retries=2,
        retry_delay_seconds=10,
        rationale=(
            "Subscription / mandate payment failed. Policy: retry up to 2 times with a "
            "short delay — mandate failures are often transient (insufficient balance at "
            "debit time, brief bank downtime). The retry window is intentionally short to "
            "keep within the same business day. If both retries fail, escalate rather than "
            "sending a generic payment link, since mandate re-registration may be required "
            "and must be handled by the merchant's subscription system."
        ),
    ),
    RootCauseCategory.UNKNOWN: RecoveryPolicy(
        action=RecoveryAction.PAYMENT_LINK,
        max_retries=0,
        retry_delay_seconds=0,
        rationale=(
            "Root cause could not be classified. Policy: safe default is to send a "
            "payment link rather than auto-retrying an unknown failure. Escalate "
            "if the link is not used within the expiry window."
        ),
    ),
}


def get_policy(category: RootCauseCategory) -> RecoveryPolicy:
    """
    Look up the RecoveryPolicy for a given root-cause category.

    Falls back to the UNKNOWN policy if somehow a category has no entry
    (defensive programming — should never happen with a complete table).
    """
    return POLICY_TABLE.get(category, POLICY_TABLE[RootCauseCategory.UNKNOWN])


def should_retry(policy: RecoveryPolicy, current_retry_count: int) -> bool:
    """
    Return True if the policy allows another retry given the current count.

    This is the single authoritative gate that the executor must call
    before attempting any retry — enforces the hard cap.
    """
    return (
        policy.action in (RecoveryAction.IMMEDIATE_RETRY, RecoveryAction.RETRY_THEN_LINK)
        and current_retry_count < policy.max_retries
    )


def should_send_link_after_retries(
    policy: RecoveryPolicy, current_retry_count: int
) -> bool:
    """
    Return True if retries are exhausted and the policy calls for a fallback link.

    Only RETRY_THEN_LINK sends a link after retry exhaustion.
    """
    return (
        policy.action == RecoveryAction.RETRY_THEN_LINK
        and current_retry_count >= policy.max_retries
    )


HIGH_VALUE_THRESHOLD_PAISE = 1000000  # ₹10,000 INR


def is_high_value_transaction(amount_paise: int) -> bool:
    """Check if transaction amount exceeds high-value threshold (≥ ₹10,000)."""
    return amount_paise >= HIGH_VALUE_THRESHOLD_PAISE

