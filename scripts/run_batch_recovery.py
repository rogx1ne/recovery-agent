"""
scripts/run_batch_recovery.py
──────────────────────────────
Runs the full recovery pipeline for a list of transaction IDs by calling
POST /api/v1/recovery/{id} for each one, then prints a formatted summary.

Usage
-----
    # Run recovery for specific IDs:
    python scripts/run_batch_recovery.py --ids 1 2 3 4 5

    # Run recovery for ALL failed transactions:
    python scripts/run_batch_recovery.py --all

    # Combine with generate_batch.py for a full end-to-end test:
    python scripts/generate_batch.py && python scripts/run_batch_recovery.py --all

What it does
------------
1. Fetches the list of transactions in 'failed' status (if --all).
2. POSTs to the recovery endpoint for each.
3. Prints a detailed audit trail for each transaction.
4. Prints a final batch summary using GET /api/v1/metrics/summary.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error


def get_json(url: str) -> tuple[int, dict | list]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def post_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def fetch_failed_ids(base_url: str) -> list[int]:
    status, data = get_json(f"{base_url}/api/v1/transactions/?status=failed&limit=500")
    if status != 200:
        print(f"  ✗ Could not fetch failed transactions: {data}")
        return []
    items = data.get("items", [])
    return [item["id"] for item in items]


def fetch_audit_trail(base_url: str, tx_id: int) -> list[dict]:
    status, data = get_json(f"{base_url}/api/v1/audit/transaction/{tx_id}")
    if status != 200:
        return []
    return data.get("items", [])


def run_recovery_for(base_url: str, tx_id: int) -> tuple[int, dict]:
    return post_json(f"{base_url}/api/v1/recovery/{tx_id}")


def print_audit_trail(logs: list[dict]):
    for log in logs:
        step = log.get("step", "?").upper()
        detail = log.get("detail", "")
        reasoning = log.get("reasoning", "")
        ts = log.get("timestamp", "")[:19]
        print(f"      [{ts}] {step}")
        print(f"        Detail   : {detail}")
        print(f"        Reasoning: {reasoning}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Run batch recovery pipeline")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--ids", nargs="*", type=int, default=[], help="Specific transaction IDs")
    parser.add_argument("--all", action="store_true", help="Recover all 'failed' transactions")
    parser.add_argument("--show-audit", action="store_true", default=True, help="Print full audit trail per transaction")
    args = parser.parse_args()

    base_url = args.api_url.rstrip("/")

    if args.all:
        print("  Fetching all failed transactions...")
        tx_ids = fetch_failed_ids(base_url)
        if not tx_ids:
            print("  No failed transactions found. Run generate_batch.py first.")
            return 0
    elif args.ids:
        tx_ids = args.ids
    else:
        parser.print_help()
        return 1

    print(f"\n{'='*65}")
    print(f"  Recovery Agent — Batch Recovery Runner")
    print(f"  API: {base_url}")
    print(f"  Processing {len(tx_ids)} transaction(s): {tx_ids}")
    print(f"{'='*65}\n")

    results = []
    for tx_id in tx_ids:
        print(f"  ── Transaction {tx_id} ──────────────────────────────────────")
        status_code, resp = run_recovery_for(base_url, tx_id)

        if status_code == 200:
            final = resp.get("final_status", "?")
            rzp_id = resp.get("razorpay_payment_id", "?")
            artefacts = resp.get("artefacts", {})
            steps = resp.get("steps_taken", [])
            print(f"  ✓ Status: {final.upper()}  |  payment_id={rzp_id}")
            print(f"  Steps  : {' → '.join(steps)}")
            if artefacts:
                print(f"  Artefacts:")
                for k, v in artefacts.items():
                    print(f"    {k}: {v}")
        else:
            print(f"  ✗ Recovery failed ({status_code}): {resp.get('detail', resp)}")
            final = "error"

        results.append({"tx_id": tx_id, "final_status": final, "http_status": status_code})

        if args.show_audit and status_code == 200:
            logs = fetch_audit_trail(base_url, tx_id)
            if logs:
                print(f"\n  Audit Trail ({len(logs)} entries):")
                print_audit_trail(logs)

    # ── Batch summary ──────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  BATCH SUMMARY")
    print(f"{'='*65}")
    status_c, metrics = get_json(f"{base_url}/api/v1/metrics/summary")
    if status_c == 200:
        print(f"  Total transactions    : {metrics.get('total_transactions', 0)}")
        print(f"  Recovered             : {metrics['by_status'].get('recovered', 0)}")
        print(f"  Escalated             : {metrics['by_status'].get('escalated', 0)}")
        print(f"  Still failed          : {metrics['by_status'].get('failed', 0)}")
        print(f"  Recovery rate         : {metrics.get('recovery_rate_pct', 0)}%")
        print(f"  Amount recovered      : ₹{metrics.get('amount_recovered_inr', 0)}")
    print(f"{'='*65}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
