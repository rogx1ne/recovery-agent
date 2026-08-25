"""
tests/test_decision_policy.py — Unit tests for the decision policy table.
"""

import pytest
from app.models.transaction import RootCauseCategory
from app.services.decision_policy import (
    RecoveryAction,
    get_policy,
    should_retry,
    should_send_link_after_retries,
)


class TestGetPolicy:
    """Every category must have a policy with a finite max_retries."""

    @pytest.mark.parametrize("category", list(RootCauseCategory))
    def test_all_categories_have_policy(self, category):
        policy = get_policy(category)
        assert policy is not None
        assert policy.max_retries >= 0

    def test_card_declined_is_retry_then_link(self):
        p = get_policy(RootCauseCategory.CARD_DECLINED)
        assert p.action == RecoveryAction.RETRY_THEN_LINK
        assert p.max_retries == 1

    def test_insufficient_fund_is_payment_link_no_retry(self):
        p = get_policy(RootCauseCategory.INSUFFICIENT_FUND)
        assert p.action == RecoveryAction.PAYMENT_LINK
        assert p.max_retries == 0

    def test_gateway_error_is_immediate_retry(self):
        p = get_policy(RootCauseCategory.GATEWAY_TECHNICAL_ERROR)
        assert p.action == RecoveryAction.IMMEDIATE_RETRY
        assert p.max_retries == 2

    def test_auth_failed_is_payment_link_no_retry(self):
        p = get_policy(RootCauseCategory.AUTHENTICATION_FAILED)
        assert p.action == RecoveryAction.PAYMENT_LINK
        assert p.max_retries == 0

    def test_subscription_failed_is_immediate_retry(self):
        p = get_policy(RootCauseCategory.SUBSCRIPTION_FAILED)
        assert p.action == RecoveryAction.IMMEDIATE_RETRY
        assert p.max_retries == 2

    def test_all_policies_have_non_empty_rationale(self):
        for category in RootCauseCategory:
            p = get_policy(category)
            assert len(p.rationale) > 20, f"Rationale too short for {category}"


class TestShouldRetry:
    """Verify the retry gate enforces hard caps."""

    def test_gateway_error_allows_two_retries(self):
        p = get_policy(RootCauseCategory.GATEWAY_TECHNICAL_ERROR)
        assert should_retry(p, 0) is True
        assert should_retry(p, 1) is True
        assert should_retry(p, 2) is False  # cap reached

    def test_card_declined_allows_one_retry(self):
        p = get_policy(RootCauseCategory.CARD_DECLINED)
        assert should_retry(p, 0) is True
        assert should_retry(p, 1) is False

    def test_payment_link_policy_never_retries(self):
        p = get_policy(RootCauseCategory.INSUFFICIENT_FUND)
        assert should_retry(p, 0) is False

    def test_auth_failed_never_retries(self):
        p = get_policy(RootCauseCategory.AUTHENTICATION_FAILED)
        assert should_retry(p, 0) is False


class TestShouldSendLinkAfterRetries:
    """RETRY_THEN_LINK should fallback to link when retries exhausted."""

    def test_card_declined_sends_link_after_retry_exhausted(self):
        p = get_policy(RootCauseCategory.CARD_DECLINED)
        assert should_send_link_after_retries(p, 1) is True

    def test_gateway_error_does_not_send_link(self):
        p = get_policy(RootCauseCategory.GATEWAY_TECHNICAL_ERROR)
        assert should_send_link_after_retries(p, 2) is False

    def test_insufficient_fund_does_not_send_link_after_retries(self):
        # PAYMENT_LINK action, but should_send_link_after_retries checks for RETRY_THEN_LINK
        p = get_policy(RootCauseCategory.INSUFFICIENT_FUND)
        assert should_send_link_after_retries(p, 0) is False
