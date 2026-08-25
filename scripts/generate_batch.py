"""
scripts/generate_batch.py
─────────────────────────
Generates a batch of test failed transactions by POSTing directly to the
Recovery Agent API.  Uses Razorpay's documented test-mode magic payment IDs
and simulated failure reason codes (no real Razorpay calls needed here —
the IDs are pre-assigned to known failure scenarios in test mode).

Usage
-----
    # From recovery-agent/ directory with the server running:
    python scripts/generate_batch.py [--api-url http://localhost:8000] [--count N]

What it does
------------
1. Defines a set of test cases covering all four root-cause categories.
2. POSTs each one to POST /api/v1/transactions/ to register them.
3. Prints a summary table with the created transaction IDs.

Test payment IDs
----------------
Razorpay's test mode accepts any payment ID prefixed with 'pay_' —
the exact IDs below are illustrative.  The failure_reason_code values
drive the classifier, not the payment ID itself.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ─── Test scenarios ───────────────────────────────────────────────────────────
# Each dict maps to the TransactionCreate schema.
# Amounts are in paise (₹100 = 10000 paise).

TEST_CASES = [
    # card_declined scenarios
    {
        "razorpay_payment_id": f"pay_TestCardDecline001",
        "amount": 50000,   # ₹500
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "card_declined",
        "_label": "Card Declined (basic)",
    },
    {
        "razorpay_payment_id": f"pay_TestCardDecline002",
        "amount": 120000,  # ₹1200
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "do_not_honour",
        "_label": "Card Declined (do_not_honour)",
    },
    # insufficient_fund scenarios
    {
        "razorpay_payment_id": f"pay_TestInsufficientFund001",
        "amount": 250000,  # ₹2500
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "insufficient_funds",
        "_label": "Insufficient Funds",
    },
    # gateway_technical_error scenarios
    {
        "razorpay_payment_id": f"pay_TestGatewayErr001",
        "amount": 75000,   # ₹750
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "gateway_technical_error",
        "_label": "Gateway Technical Error",
    },
    {
        "razorpay_payment_id": f"pay_TestGatewayErr002",
        "amount": 30000,   # ₹300
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "network_error",
        "_label": "Gateway Error (network_error)",
    },
    # authentication_failed scenarios
    {
        "razorpay_payment_id": f"pay_TestAuthFail001",
        "amount": 99900,   # ₹999
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "authentication_failed",
        "_label": "Authentication Failed",
    },
    {
        "razorpay_payment_id": f"pay_TestAuthFail002",
        "amount": 15000,   # ₹150
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "invalid_otp",
        "_label": "Authentication Failed (invalid_otp)",
    },
    # unknown / edge case
    {
        "razorpay_payment_id": f"pay_TestUnknown001",
        "amount": 5000,    # ₹50
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "some_new_undocumented_reason",
        "_label": "Unknown failure reason",
    },
]


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    """Simple urllib POST to avoid external dependencies in scripts."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    parser = argparse.ArgumentParser(description="Generate a batch of test failed transactions")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL of the Recovery Agent API")
    parser.add_argument("--count", type=int, default=len(TEST_CASES), help="Number of test cases to create (max: all)")
    args = parser.parse_args()

    base_url = args.api_url.rstrip("/")
    endpoint = f"{base_url}/api/v1/transactions/"
    cases = TEST_CASES[: args.count]

    # Add timestamp suffix to payment IDs to avoid conflicts on re-runs
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for case in cases:
        case["razorpay_payment_id"] = f"{case['razorpay_payment_id']}_{ts}"

    print(f"\n{'='*60}")
    print(f"  Recovery Agent — Batch Generator")
    print(f"  API: {base_url}")
    print(f"  Creating {len(cases)} test transactions...")
    print(f"{'='*60}\n")

    created_ids = []
    for i, case in enumerate(cases, 1):
        label = case.pop("_label")
        status_code, resp = post_json(endpoint, case)

        if status_code == 201:
            tx_id = resp.get("id")
            created_ids.append(tx_id)
            print(f"  [{i:02d}] ✓ Created tx_id={tx_id} | {label}")
            print(f"       payment_id={case['razorpay_payment_id']}")
            print(f"       failure_reason={case['failure_reason_code']}  amount=₹{case['amount']//100}")
        else:
            print(f"  [{i:02d}] ✗ FAILED ({status_code}) | {label}")
            print(f"       {resp}")
        print()

    print(f"{'='*60}")
    print(f"  Done. Created IDs: {created_ids}")
    print(f"  Run the recovery pipeline with:")
    print(f"    python scripts/run_batch_recovery.py --ids {' '.join(str(i) for i in created_ids)}")
    print(f"{'='*60}\n")

    return 0 if len(created_ids) == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
