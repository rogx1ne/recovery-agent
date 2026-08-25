"""
tests/test_classifier.py — Unit tests for the classifier service.
No external calls, no database — pure logic tests.
"""

import pytest
from app.models.transaction import RootCauseCategory
from app.services.classifier import classify, explain_classification


class TestClassify:
    """Tests for classify()."""

    @pytest.mark.parametrize("reason,expected", [
        ("card_declined", RootCauseCategory.CARD_DECLINED),
        ("CARD_DECLINED", RootCauseCategory.CARD_DECLINED),
        ("do_not_honour", RootCauseCategory.CARD_DECLINED),
        ("restricted_card", RootCauseCategory.CARD_DECLINED),
        ("insufficient_funds", RootCauseCategory.INSUFFICIENT_FUND),
        ("low balance", RootCauseCategory.INSUFFICIENT_FUND),
        ("gateway_technical_error", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
        ("network_error", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
        ("timeout", RootCauseCategory.GATEWAY_TECHNICAL_ERROR),
        ("authentication_failed", RootCauseCategory.AUTHENTICATION_FAILED),
        ("invalid_otp", RootCauseCategory.AUTHENTICATION_FAILED),
        ("payment_cancelled", RootCauseCategory.AUTHENTICATION_FAILED),
        ("mandate_failed", RootCauseCategory.SUBSCRIPTION_FAILED),
        ("subscription_failed", RootCauseCategory.SUBSCRIPTION_FAILED),
        ("autopay_failure", RootCauseCategory.SUBSCRIPTION_FAILED),
        ("some_completely_unknown_reason", RootCauseCategory.UNKNOWN),
        ("", RootCauseCategory.UNKNOWN),
        (None, RootCauseCategory.UNKNOWN),
    ])
    def test_classify_known_reasons(self, reason, expected):
        assert classify(reason) == expected

    def test_insufficient_fund_takes_priority_over_card_declined(self):
        # A reason that mentions "insufficient" should not match "card_declined"
        result = classify("insufficient_funds")
        assert result == RootCauseCategory.INSUFFICIENT_FUND


class TestExplainClassification:
    """Tests for explain_classification()."""

    def test_unknown_explanation_mentions_fallback(self):
        explanation = explain_classification("weird_reason", RootCauseCategory.UNKNOWN)
        assert "UNKNOWN" in explanation or "unknown" in explanation

    def test_known_category_explanation_mentions_category(self):
        explanation = explain_classification(
            "card_declined", RootCauseCategory.CARD_DECLINED
        )
        assert "card_declined" in explanation

    def test_returns_string(self):
        result = explain_classification(None, RootCauseCategory.UNKNOWN)
        assert isinstance(result, str)
        assert len(result) > 0
