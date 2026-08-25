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
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.demo_seed import DEMO_BATCH_CASES, generate_batch_id


# ─── Colour helpers (ANSI, gracefully degraded on Windows) ───────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

GREEN  = lambda t: _c("32;1", t)
RED    = lambda t: _c("31;1", t)
YELLOW = lambda t: _c("33;1", t)
CYAN   = lambda t: _c("36;1", t)
BOLD   = lambda t: _c("1", t)
DIM    = lambda t: _c("2", t)


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
    batch_id = generate_batch_id()
    suffix = batch_id.replace("batch_", "")

    print()
    print(BOLD("═" * 65))
    print(BOLD("  🤖  Recovery Agent — Live Demo"))
    print(BOLD(f"  API: {base}"))
    print(BOLD(f"  Batch ID: {batch_id}"))
    print(BOLD("═" * 65))

    # ── PHASE 1: Create failed transactions ────────────────────────────────
    print(f"\n{CYAN('PHASE 1')} — Registering {len(DEMO_BATCH_CASES)} failed transactions (batch: {batch_id})\n")

    total_at_risk = 0
    created: list[dict] = []

    for i, case in enumerate(DEMO_BATCH_CASES, 1):
        label = case["label"]
        category = case["category"]
        payload = {
            "razorpay_payment_id": f"{case['base_payment_id']}_{suffix}",
            "amount": case["amount"],
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": case["failure_reason_code"],
            "batch_id": batch_id,
            "customer_contact": case["customer_contact"],
            "customer_email": case["customer_email"],
            "customer_name": case["customer_name"],
        }

        status_code, resp = _post(f"{base}/api/v1/transactions/", payload)

        if status_code == 201:
            tx_id = resp["id"]
            amount_inr = case["amount"] / 100
            total_at_risk += case["amount"]
            created.append({
                "id": tx_id,
                "label": label,
                "amount": case["amount"],
                "payment_id": payload["razorpay_payment_id"],
                "category": category,
            })
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

    for tx in created:
        print(f"  Processing tx {tx['id']} — {tx['label']}...")
        status_code, resp = _post(f"{base}/api/v1/recovery/{tx['id']}", {})

        if status_code == 200:
            final = resp.get("final_status", "?")
            artefacts = resp.get("artefacts", {})

            colour = CYAN if final in ("retry_initiated", "link_sent") else YELLOW if final == "escalated" else GREEN
            error_hint = ""
            if final == "escalated" and artefacts.get("payment_link_error"):
                error_hint = f" — {RED(artefacts['payment_link_error'])}"
            print(f"    → {colour(final.upper())}{error_hint}  steps: {' → '.join(resp.get('steps_taken', []))}")

            if artefacts.get("payment_link_url"):
                print(f"    → Link: {DIM(artefacts['payment_link_url'])}")
            if artefacts.get("retry_order_id"):
                print(f"    → Order: {DIM(artefacts['retry_order_id'])}")

            results.append({**tx, "final_status": final, "artefacts": artefacts})
        else:
            print(f"    → {RED('ERROR')} ({status_code}): {resp.get('detail')}")
            results.append({**tx, "final_status": "error", "artefacts": {}})

        time.sleep(0.2)

    # ── PHASE 2.5: Simulate Webhook Confirmations ─────────────────────────
    print(f"\n{CYAN('PHASE 2.5')} — Simulating Webhook Payment Confirmations\n")
    print("  (Simulating payment completion for a subset of initiated/link_sent transactions)\n")

    confirmed_count = 0
    # Simulate payment completion for 5 of the non-escalated transactions
    webhook_candidates = [r for r in results if r["final_status"] in ("retry_initiated", "link_sent")][:5]

    for tx in webhook_candidates:
        payment_id = tx["payment_id"]
        artefacts = tx["artefacts"]

        if tx["final_status"] == "link_sent" and artefacts.get("payment_link_id"):
            link_id = artefacts["payment_link_id"]
            payload = {
                "event": "payment_link.paid",
                "payload": {
                    "payment_link": {
                        "entity": {
                            "id": link_id,
                            "reference_id": f"recovery_{payment_id}",
                            "amount_paid": tx["amount"],
                        }
                    }
                },
            }
        else:
            payload = {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"pay_captured_{tx['id']}",
                            "notes": {"original_payment_id": payment_id},
                        }
                    }
                },
            }

        code, wb_resp = _post(f"{base}/api/v1/webhooks/razorpay", payload)
        if code == 200 and wb_resp.get("action") in ("marked_recovered", "already_recovered"):
            tx["final_status"] = "recovered"
            confirmed_count += 1
            print(f"  {GREEN('✓')} Webhook confirmed tx_id={tx['id']:3d}  {tx['label']} → {GREEN('RECOVERED')}")
        else:
            print(f"  {RED('✗')} Webhook failed for tx_id={tx['id']:3d}: {wb_resp}")

    print(f"\n  {GREEN(f'{confirmed_count} payments confirmed via webhook.')}")

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

    # ── PHASE 4: Final metrics summary (Batch-Scoped from API) ─────────────
    print(BOLD("═" * 65))
    print(BOLD(f"  📊  BATCH RESULTS SUMMARY (Batch: {batch_id})"))
    print(BOLD("═" * 65))

    status_code, stats = _get(f"{base}/api/v1/stats/summary?batch_id={batch_id}")
    if status_code == 200:
        by_status = stats.get("by_status", {})
        rec_count = by_status.get("recovered", 0)
        pending_conf_count = by_status.get("pending_confirmation", 0)
        esc_count = by_status.get("escalated", 0)
        total_tx = stats.get("total_transactions", 0)

        amt_rec_inr = stats.get("amount_recovered_inr", 0.0)
        amt_pending_inr = stats.get("amount_pending_confirmation_inr", 0.0)
        rate_pct = stats.get("recovery_rate_pct", 0.0)
        value_rate_pct = (stats.get("amount_recovered_paise", 0) / total_at_risk * 100) if total_at_risk > 0 else 0.0
        amt_esc_inr = (total_at_risk / 100) - amt_rec_inr - amt_pending_inr

        print(f"\n  Total transactions            : {BOLD(str(total_tx))}")
        print(f"  Total at-risk                 : {RED(f'₹{total_at_risk/100:>10,.2f}')}")
        print(f"  Confirmed Recovered (Webhook) : {GREEN(f'₹{amt_rec_inr:>10,.2f}')}  ({rec_count} transactions)")
        print(f"  Awaiting Confirmation        : {CYAN(f'₹{amt_pending_inr:>10,.2f}')}  ({pending_conf_count} transactions)")
        print(f"  Escalated (Manual Review)    : {YELLOW(f'₹{amt_esc_inr:>10,.2f}')}  ({esc_count} transactions)")
        print(f"\n  {'Recovery Rate (Confirmed)':<30}: {GREEN(f'{rate_pct:.1f}%')} (count) | {GREEN(f'{value_rate_pct:.1f}%')} (value)")
    else:
        print(RED(f"Error fetching stats from API: {stats}"))

    # ── Category breakdown (Batch-Scoped from API) ─────────────────────────
    print(f"\n  {BOLD('By category:')}")
    cat_status, cat_metrics = _get(f"{base}/api/v1/stats/by-category?batch_id={batch_id}")
    if cat_status == 200:
        categories = cat_metrics.get("categories", {})
        for cat, data in sorted(categories.items()):
            counts = data.get("counts", {})
            rate = data.get("recovery_rate_pct", 0.0)
            rec = counts.get("recovered", 0)
            pending_c = data.get("pending_confirmation_count", 0)
            esc = counts.get("escalated", 0)
            total = rec + pending_c + esc
            bar_fill = "█" * int(rate / 10)
            bar_empty = "░" * (10 - int(rate / 10))
            colour = GREEN if rate >= 70 else YELLOW if rate >= 40 else RED
            print(f"    {cat:<30} [{colour(bar_fill + bar_empty)}] {colour(f'{rate:5.1f}%')}  (Confirmed: {rec}, Pending: {pending_c}, Escalated: {esc})")
    else:
        print(RED(f"Error fetching category metrics: {cat_metrics}"))

    print()
    print(BOLD("═" * 65))
    print(f"  Batch audit trail: {base}/api/v1/audit/")
    print(f"  Batch stats:       {base}/api/v1/stats/summary?batch_id={batch_id}")
    print(f"  All-time stats:    {base}/api/v1/stats/summary")
    print(f"  Swagger UI:        {base}/docs")
    print(BOLD("═" * 65))
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
