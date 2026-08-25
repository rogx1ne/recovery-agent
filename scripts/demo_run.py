"""
scripts/demo_run.py
────────────────────
One-command end-to-end demo that:
  1. Creates a batch of failed transactions across all root-cause categories
  2. Runs the full recovery pipeline on each
  3. Prints a professional before/after table with rupee amounts
  4. Dumps the AI-generated audit trail for each transaction

This is the script to run when recording your pitch video.
It produces the concrete "₹X recovered out of ₹Y at-risk" number
that the Razorpay buildathon judges expect.

Usage
-----
    # Server must be running first:
    uvicorn app.main:app --reload

    # Then in a second terminal:
    python scripts/demo_run.py
    python scripts/demo_run.py --api-url http://localhost:8000
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ─── Colour helpers (ANSI, gracefully degraded on Windows) ───────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

GREEN  = lambda t: _c("32;1", t)
RED    = lambda t: _c("31;1", t)
YELLOW = lambda t: _c("33;1", t)
CYAN   = lambda t: _c("36;1", t)
BOLD   = lambda t: _c("1", t)
DIM    = lambda t: _c("2", t)


# ─── Diverse test batch (covers all 5 categories) ────────────────────────────
DEMO_BATCH = [
    # card_declined — retry once then payment link
    {"razorpay_payment_id": "pay_Demo_CardDecline_001", "amount": 50000,
     "status": "failed", "failure_reason_code": "card_declined",
     "_label": "Card Declined", "_category": "card_declined"},

    {"razorpay_payment_id": "pay_Demo_CardDecline_002", "amount": 120000,
     "status": "failed", "failure_reason_code": "do_not_honour",
     "_label": "Card Declined (do_not_honour)", "_category": "card_declined"},

    # insufficient_fund — payment link only, no retry
    {"razorpay_payment_id": "pay_Demo_InsufficientFund_001", "amount": 250000,
     "status": "failed", "failure_reason_code": "insufficient_funds",
     "_label": "Insufficient Funds", "_category": "insufficient_fund"},

    # gateway_technical_error — immediate retry up to 2x
    {"razorpay_payment_id": "pay_Demo_GatewayErr_001", "amount": 75000,
     "status": "failed", "failure_reason_code": "gateway_technical_error",
     "_label": "Gateway Error", "_category": "gateway_technical_error"},

    {"razorpay_payment_id": "pay_Demo_GatewayErr_002", "amount": 30000,
     "status": "failed", "failure_reason_code": "network_error",
     "_label": "Network Error", "_category": "gateway_technical_error"},

    # authentication_failed — payment link with instructions
    {"razorpay_payment_id": "pay_Demo_AuthFail_001", "amount": 99900,
     "status": "failed", "failure_reason_code": "authentication_failed",
     "_label": "Auth Failed (3DS)", "_category": "authentication_failed"},

    {"razorpay_payment_id": "pay_Demo_AuthFail_002", "amount": 15000,
     "status": "failed", "failure_reason_code": "invalid_otp",
     "_label": "Auth Failed (OTP)", "_category": "authentication_failed"},

    # subscription_failed — retry mandate
    {"razorpay_payment_id": "pay_Demo_SubFail_001", "amount": 49900,
     "status": "failed", "failure_reason_code": "mandate_failed",
     "_label": "Mandate Failed", "_category": "subscription_failed"},

    {"razorpay_payment_id": "pay_Demo_SubFail_002", "amount": 199900,
     "status": "failed", "failure_reason_code": "recurring_charge_failed",
     "_label": "Recurring Charge Failed", "_category": "subscription_failed"},

    # unknown
    {"razorpay_payment_id": "pay_Demo_Unknown_001", "amount": 5000,
     "status": "failed", "failure_reason_code": "undocumented_issuer_code_42",
     "_label": "Unknown Error", "_category": "unknown"},
]


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(url: str) -> tuple[int, dict | list]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Recovery Agent — End-to-End Demo")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.api_url.rstrip("/")

    # Unique suffix to avoid conflicts on re-runs
    ts = datetime.now(timezone.utc).strftime("%H%M%S")

    print()
    print(BOLD("═" * 65))
    print(BOLD("  🤖  Recovery Agent — Live Demo"))
    print(BOLD(f"  API: {base}"))
    print(BOLD("═" * 65))

    # ── PHASE 1: Create failed transactions ────────────────────────────────
    print(f"\n{CYAN('PHASE 1')} — Registering {len(DEMO_BATCH)} failed transactions\n")

    total_at_risk = 0
    created: list[dict] = []

    for i, case in enumerate(DEMO_BATCH, 1):
        label = case.pop("_label")
        category = case.pop("_category")
        case["razorpay_payment_id"] += f"_{ts}"
        case["currency"] = "INR"

        status_code, resp = _post(f"{base}/api/v1/transactions/", case)

        if status_code == 201:
            tx_id = resp["id"]
            amount_inr = case["amount"] / 100
            total_at_risk += case["amount"]
            created.append({"id": tx_id, "label": label, "amount": case["amount"],
                             "payment_id": case["razorpay_payment_id"], "category": category})
            print(f"  {GREEN('✓')} [{i:02d}] tx_id={tx_id:3d}  ₹{amount_inr:8,.2f}  {label}")
        else:
            print(f"  {RED('✗')} [{i:02d}] FAILED ({status_code}) — {label}: {resp.get('detail')}")

    print(f"\n  {BOLD('Total at-risk:')} {RED(f'₹{total_at_risk/100:,.2f}')}")

    if not created:
        print(RED("\nNo transactions created. Is the server running?"))
        return 1

    # ── PHASE 2: Run recovery pipeline ────────────────────────────────────
    print(f"\n{CYAN('PHASE 2')} — Running recovery pipeline\n")

    results: list[dict] = []
    total_recovered_paise = 0
    total_escalated_paise = 0

    for tx in created:
        print(f"  Processing tx {tx['id']} — {tx['label']}...")
        status_code, resp = _post(f"{base}/api/v1/recovery/{tx['id']}", {})

        if status_code == 200:
            final = resp.get("final_status", "?")
            artefacts = resp.get("artefacts", {})

            colour = GREEN if final == "recovered" else YELLOW if final == "escalated" else RED
            print(f"    → {colour(final.upper())}  steps: {' → '.join(resp.get('steps_taken', []))}")

            if artefacts.get("payment_link_url"):
                print(f"    → Link: {DIM(artefacts['payment_link_url'])}")
            if artefacts.get("retry_order_id"):
                print(f"    → Order: {DIM(artefacts['retry_order_id'])}")

            if final == "recovered":
                total_recovered_paise += tx["amount"]
            elif final == "escalated":
                total_escalated_paise += tx["amount"]

            results.append({**tx, "final_status": final, "artefacts": artefacts})
        else:
            print(f"    → {RED('ERROR')} ({status_code}): {resp.get('detail')}")
            results.append({**tx, "final_status": "error", "artefacts": {}})

        time.sleep(0.3)   # brief pause between API calls

    # ── PHASE 3: Detailed audit trails ────────────────────────────────────
    print(f"\n{CYAN('PHASE 3')} — AI-generated audit trails\n")

    for tx in results[:3]:   # show first 3 to keep demo concise
        _, audit = _get(f"{base}/api/v1/audit/transaction/{tx['id']}")
        logs = audit.get("items", [])
        tx_id   = tx["id"]
        tx_label = tx["label"]
        print(f"  {BOLD(f'Transaction {tx_id} — {tx_label}')}")
        for log in logs:
            step = log["step"].upper()
            ts_short = log["timestamp"][:19].replace("T", " ")
            reasoning_preview = log["reasoning"][:120].replace("\n", " ")
            ellipsis = "..." if len(log["reasoning"]) > 120 else ""
            print(f"    [{ts_short}] {CYAN(step)}")
            print(f"      {DIM(reasoning_preview)}{ellipsis}")
        print()

    # ── PHASE 4: Final metrics summary ────────────────────────────────────
    print(BOLD("═" * 65))
    print(BOLD("  📊  BATCH RESULTS SUMMARY"))
    print(BOLD("═" * 65))

    recovered_count = sum(1 for r in results if r["final_status"] == "recovered")
    escalated_count = sum(1 for r in results if r["final_status"] == "escalated")
    error_count     = sum(1 for r in results if r["final_status"] == "error")
    recovery_rate   = (recovered_count / len(results) * 100) if results else 0
    money_rate      = (total_recovered_paise / total_at_risk * 100) if total_at_risk else 0

    print(f"\n  Total transactions    : {BOLD(str(len(results)))}")
    print(f"  Total at-risk         : {RED(f'₹{total_at_risk/100:>10,.2f}')}")
    print(f"  Recovered             : {GREEN(f'₹{total_recovered_paise/100:>10,.2f}')}  ({recovered_count} transactions)")
    print(f"  Escalated             : {YELLOW(f'₹{total_escalated_paise/100:>10,.2f}')}  ({escalated_count} transactions — manual review)")
    if error_count:
        print(f"  Errors                : {RED(str(error_count))} transactions")
    print(f"\n  {'Recovery rate (count)':<24}: {GREEN(f'{recovery_rate:.1f}%')}")
    print(f"  {'Recovery rate (value)':<24}: {GREEN(f'{money_rate:.1f}%')}")

    # ── Category breakdown ─────────────────────────────────────────────────
    print(f"\n  {BOLD('By category:')}")
    _, cat_metrics = _get(f"{base}/api/v1/metrics/by-category")
    categories = cat_metrics.get("categories", {})
    for cat, data in sorted(categories.items()):
        counts = data.get("counts", {})
        rate = data.get("recovery_rate_pct", 0)
        rec = counts.get("recovered", 0)
        esc = counts.get("escalated", 0)
        total = rec + esc + counts.get("failed", 0)
        bar_fill = "█" * int(rate / 10)
        bar_empty = "░" * (10 - int(rate / 10))
        colour = GREEN if rate >= 70 else YELLOW if rate >= 40 else RED
        print(f"    {cat:<30} [{colour(bar_fill + bar_empty)}] {colour(f'{rate:5.1f}%')}  ({rec}/{total})")

    print()
    print(BOLD("═" * 65))
    print(f"  Full audit trail: {base}/api/v1/audit/")
    print(f"  Metrics:          {base}/api/v1/metrics/summary")
    print(f"  Swagger UI:       {base}/docs")
    print(BOLD("═" * 65))
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
