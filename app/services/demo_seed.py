"""
services/demo_seed.py — Shared test batch definition and runner with live step streaming.

Used by both:
  - scripts/demo_run.py (CLI runner)
  - app/routers/demo.py (Frontend "Run Demo Batch" button / API)

Maintains single source of truth for the 10 demo transactions,
recovery execution, real webhook handler dispatch, and live progress state.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.transaction import Transaction, TransactionStatus
from app.services.executor import run_recovery

logger = logging.getLogger(__name__)

# ─── Diverse 10-case test batch (covers all 5 failure categories) ─────────────
DEMO_BATCH_CASES: list[dict[str, Any]] = [
    # card_declined — retry once then payment link
    {
        "base_payment_id": "pay_Demo_CardDecline_001",
        "amount": 50000,  # ₹500.00
        "failure_reason_code": "card_declined",
        "customer_contact": "+919876543210",
        "customer_email": "aarav.patel@example.com",
        "customer_name": "Aarav Patel",
        "label": "Card Declined",
        "category": "card_declined",
    },
    {
        "base_payment_id": "pay_Demo_CardDecline_002",
        "amount": 120000,  # ₹1,200.00
        "failure_reason_code": "do_not_honour",
        "customer_contact": "+919812345678",
        "customer_email": "neha.sharma@example.com",
        "customer_name": "Neha Sharma",
        "label": "Card Declined (do_not_honour)",
        "category": "card_declined",
    },
    # insufficient_fund — payment link only, no retry
    {
        "base_payment_id": "pay_Demo_InsufficientFund_001",
        "amount": 250000,  # ₹2,500.00
        "failure_reason_code": "insufficient_funds",
        "customer_contact": "+919734567890",
        "customer_email": "rohan.gupta@example.com",
        "customer_name": "Rohan Gupta",
        "label": "Insufficient Funds",
        "category": "insufficient_fund",
    },
    # gateway_technical_error — immediate retry up to 2x
    {
        "base_payment_id": "pay_Demo_GatewayErr_001",
        "amount": 75000,  # ₹750.00
        "failure_reason_code": "gateway_technical_error",
        "customer_contact": "+919623456789",
        "customer_email": "priya.verma@example.com",
        "customer_name": "Priya Verma",
        "label": "Gateway Error",
        "category": "gateway_technical_error",
    },
    {
        "base_payment_id": "pay_Demo_GatewayErr_002",
        "amount": 30000,  # ₹300.00
        "failure_reason_code": "network_error",
        "customer_contact": "+919534567890",
        "customer_email": "vikram.m@example.com",
        "customer_name": "Vikram Malhotra",
        "label": "Network Error",
        "category": "gateway_technical_error",
    },
    # authentication_failed — payment link with instructions
    {
        "base_payment_id": "pay_Demo_AuthFail_001",
        "amount": 99900,  # ₹999.00
        "failure_reason_code": "authentication_failed",
        "customer_contact": "+919423456781",
        "customer_email": "ananya.iyer@example.com",
        "customer_name": "Ananya Iyer",
        "label": "Auth Failed (3DS)",
        "category": "authentication_failed",
    },
    {
        "base_payment_id": "pay_Demo_AuthFail_002",
        "amount": 15000,  # ₹150.00
        "failure_reason_code": "invalid_otp",
        "customer_contact": "+919312345672",
        "customer_email": "karan.joshi@example.com",
        "customer_name": "Karan Joshi",
        "label": "Auth Failed (OTP)",
        "category": "authentication_failed",
    },
    # subscription_failed — retry mandate
    {
        "base_payment_id": "pay_Demo_SubFail_001",
        "amount": 49900,  # ₹499.00
        "failure_reason_code": "mandate_failed",
        "customer_contact": "+919234567813",
        "customer_email": "divya.nair@example.com",
        "customer_name": "Divya Nair",
        "label": "Mandate Failed",
        "category": "subscription_failed",
    },
    {
        "base_payment_id": "pay_Demo_SubFail_002",
        "amount": 199900,  # ₹1,999.00
        "failure_reason_code": "recurring_charge_failed",
        "customer_contact": "+919123456784",
        "customer_email": "aditya.rao@example.com",
        "customer_name": "Aditya Rao",
        "label": "Recurring Charge Failed",
        "category": "subscription_failed",
    },
    # unknown
    {
        "base_payment_id": "pay_Demo_Unknown_001",
        "amount": 5000,  # ₹50.00
        "failure_reason_code": "undocumented_issuer_code_42",
        "customer_contact": "+919012345675",
        "customer_email": "sneha.k@example.com",
        "customer_name": "Sneha Kulkarni",
        "label": "Unknown Error",
        "category": "unknown",
    },
]

# ─── Live Progress State Store ───────────────────────────────────────────────
_DEMO_BATCH_STATUS: dict[str, dict[str, Any]] = {}


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _append_log(batch_id: str, log_type: str, message: str, detail: str = ""):
    if batch_id not in _DEMO_BATCH_STATUS:
        return
    _DEMO_BATCH_STATUS[batch_id]["logs"].append({
        "time": _now_str(),
        "type": log_type,
        "message": message,
        "detail": detail,
    })


def get_demo_batch_live_status(batch_id: str, db: Session | None = None) -> dict[str, Any]:
    """
    Returns live progress object containing current phase, action, percentage, and log feed.
    """
    if batch_id in _DEMO_BATCH_STATUS:
        return _DEMO_BATCH_STATUS[batch_id]

    # Fallback if status not in memory
    total = len(DEMO_BATCH_CASES)
    if db is not None:
        txs = db.query(Transaction).filter(Transaction.batch_id == batch_id).all()
        completed_count = sum(
            1 for tx in txs
            if tx.status not in (TransactionStatus.FAILED, TransactionStatus.PENDING)
        )
        is_completed = (len(txs) == total and completed_count == total)
        return {
            "batch_id": batch_id,
            "total": total,
            "completed": completed_count,
            "percent": 100 if is_completed else int((completed_count / total) * 100),
            "status": "completed" if is_completed else "running",
            "phase": "Completed" if is_completed else "Processing",
            "current_action": "Batch processed" if is_completed else "Processing transactions...",
            "logs": [],
        }

    return {
        "batch_id": batch_id,
        "total": total,
        "completed": 0,
        "percent": 0,
        "status": "running",
        "phase": "Initializing",
        "current_action": "Preparing demo transactions...",
        "logs": [],
    }


def generate_batch_id() -> str:
    """Generate a clean batch identifier string with UTC timestamp."""
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    return f"batch_{ts}"


def create_demo_transactions(db: Session, batch_id: str) -> list[Transaction]:
    """
    Create and insert the 10 demo transactions tagged with batch_id.
    """
    suffix = batch_id.replace("batch_", "")
    transactions: list[Transaction] = []

    _DEMO_BATCH_STATUS[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total": len(DEMO_BATCH_CASES),
        "completed": 0,
        "percent": 5,
        "phase": "Phase 1/3: Ingesting Failed Payments",
        "current_action": "Creating 10 synthetic failed payment transactions across all 5 failure categories...",
        "logs": [],
    }
    _append_log(
        batch_id,
        "init",
        "Created 10 synthetic failed transactions (Card Declined, Insufficient Funds, Gateway Errors, Auth Failures, Subscriptions)",
    )

    for case in DEMO_BATCH_CASES:
        rzp_id = f"{case['base_payment_id']}_{suffix}"
        tx = Transaction(
            razorpay_payment_id=rzp_id,
            amount=case["amount"],
            currency="INR",
            status=TransactionStatus.FAILED,
            failure_reason_code=case["failure_reason_code"],
            batch_id=batch_id,
            customer_contact=case["customer_contact"],
            customer_email=case["customer_email"],
            customer_name=case["customer_name"],
        )
        db.add(tx)
        transactions.append(tx)

    db.commit()
    for tx in transactions:
        db.refresh(tx)

    logger.info("Created %d demo transactions for batch %s", len(transactions), batch_id)
    return transactions


def execute_demo_pipeline(db: Session, transactions: list[Transaction]) -> list[dict]:
    """
    Execute run_recovery() for each transaction in the list with live event logging.
    """
    results: list[dict] = []
    total = len(transactions)

    for idx, tx in enumerate(transactions, 1):
        batch_id = tx.batch_id or ""
        cust_name = tx.customer_name or "Customer"
        reason = tx.failure_reason_code or "failed"
        amount_fmt = f"₹{tx.amount / 100:,.2f}"

        if batch_id in _DEMO_BATCH_STATUS:
            _DEMO_BATCH_STATUS[batch_id]["phase"] = f"Phase 2/3: Recovery Pipeline ({idx}/{total})"
            _DEMO_BATCH_STATUS[batch_id]["current_action"] = (
                f"Analyzing Tx #{tx.id} ({cust_name} · {amount_fmt}) — Triggering AI Classification & Policy Execution..."
            )
            _append_log(
                batch_id,
                "classify",
                f"Tx #{tx.id} ({cust_name}): Analyzing failure code '{reason}' with AI classifier",
            )

        try:
            res = run_recovery(transaction_id=tx.id, db=db)
            db.refresh(tx)
            final = res.get("final_status", "?")
            artefacts = res.get("artefacts", {})

            if batch_id in _DEMO_BATCH_STATUS:
                if final == "retry_initiated":
                    order_id = artefacts.get("retry_order_id", "order_test")
                    _append_log(
                        batch_id,
                        "order",
                        f"Tx #{tx.id} ({cust_name}): Created Razorpay Retry Order {order_id} (Awaiting Payment)",
                    )
                elif final == "link_sent":
                    link_url = artefacts.get("payment_link_url", "")
                    link_id = artefacts.get("payment_link_id", "plink_test")
                    _append_log(
                        batch_id,
                        "link",
                        f"Tx #{tx.id} ({cust_name}): Generated Razorpay Recovery Link {link_id}",
                        detail=link_url,
                    )
                elif final == "escalated":
                    err_msg = artefacts.get("payment_link_error", "Manual review required")
                    _append_log(
                        batch_id,
                        "escalate",
                        f"Tx #{tx.id} ({cust_name}): Escalated — {err_msg}",
                    )

                _DEMO_BATCH_STATUS[batch_id]["completed"] = idx
                _DEMO_BATCH_STATUS[batch_id]["percent"] = min(int((idx / total) * 80) + 10, 90)

            results.append({
                "id": tx.id,
                "payment_id": tx.razorpay_payment_id,
                "amount": tx.amount,
                "final_status": res.get("final_status"),
                "artefacts": artefacts,
                "steps_taken": res.get("steps_taken", []),
            })
        except Exception as exc:
            logger.error("Error running recovery for tx %d: %s", tx.id, exc)
            if batch_id in _DEMO_BATCH_STATUS:
                _append_log(
                    batch_id,
                    "error",
                    f"Tx #{tx.id} ({cust_name}): Pipeline error: {exc}",
                )
            results.append({
                "id": tx.id,
                "payment_id": tx.razorpay_payment_id,
                "amount": tx.amount,
                "final_status": "error",
                "artefacts": {"error": str(exc)},
                "steps_taken": [],
            })
        time.sleep(0.1)

    return results


def simulate_demo_webhooks(db: Session, results: list[dict]) -> tuple[int, int]:
    """
    Simulate payment confirmation webhooks for up to 5 non-escalated transactions
    by directly exercising the authoritative Razorpay webhook handlers.

    Returns:
        tuple[int, int]: (confirmed_count, recovered_amount_paise)
    """
    from app.routers.webhooks import _handle_payment_captured, _handle_payment_link_paid

    candidates = [
        r for r in results
        if r.get("final_status") in ("retry_initiated", "link_sent")
    ][:5]

    confirmed = 0
    recovered_amount_paise = 0
    batch_id = ""

    for item in candidates:
        tx = db.get(Transaction, item["id"])
        if not tx:
            continue
        batch_id = tx.batch_id or batch_id
        artefacts = item.get("artefacts", {})

        if batch_id in _DEMO_BATCH_STATUS:
            _DEMO_BATCH_STATUS[batch_id]["phase"] = "Phase 3/3: Razorpay Webhook Simulation"
            _DEMO_BATCH_STATUS[batch_id]["current_action"] = (
                f"Processing webhook for Tx #{tx.id} ({tx.customer_name}) via Razorpay webhook pipeline..."
            )

        if item.get("final_status") == "link_sent":
            link_id = artefacts.get("payment_link_id", f"plink_sim_{tx.id}")
            payload = {
                "event": "payment_link.paid",
                "payload": {
                    "payment_link": {
                        "entity": {
                            "id": link_id,
                            "reference_id": f"rec_{tx.razorpay_payment_id}"[:40],
                            "amount_paid": tx.amount,
                        }
                    }
                },
            }
            wb_resp = _handle_payment_link_paid(payload, db)
        else:
            payload = {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"pay_captured_{tx.id}",
                            "notes": {"original_payment_id": tx.razorpay_payment_id},
                        }
                    }
                },
            }
            wb_resp = _handle_payment_captured(payload, db)

        if wb_resp.get("action") in ("marked_recovered", "already_recovered"):
            confirmed += 1
            recovered_amount_paise += tx.amount
            if batch_id in _DEMO_BATCH_STATUS:
                _append_log(
                    batch_id,
                    "webhook",
                    f"✓ Webhook confirmed payment for {tx.razorpay_payment_id} (₹{tx.amount / 100:,.2f}) → Marked RECOVERED",
                )
        else:
            logger.warning("Webhook simulation unconfirmed for tx %d: %s", tx.id, wb_resp)
            if batch_id in _DEMO_BATCH_STATUS:
                _append_log(
                    batch_id,
                    "error",
                    f"⚠ Webhook simulation unconfirmed for Tx #{tx.id}: {wb_resp.get('action')}",
                )

        time.sleep(0.15)

    logger.info("Simulated webhook confirmation for %d transactions (₹%s)", confirmed, recovered_amount_paise / 100)
    return confirmed, recovered_amount_paise


def execute_full_demo_batch(db: Session, batch_id: str) -> dict:
    """
    Full end-to-end demo execution:
      1. Create 10 transactions
      2. Run recovery pipeline
      3. Simulate webhook payment confirmation

    All statistics (amounts, percentages) are dynamically computed from live batch results.
    Any failure writes a terminal 'failed' state to _DEMO_BATCH_STATUS so frontend never hangs.
    """
    try:
        txs = create_demo_transactions(db, batch_id)
        results = execute_demo_pipeline(db, txs)
        confirmed_count, recovered_amount_paise = simulate_demo_webhooks(db, results)

        total_amount_paise = sum(tx.amount for tx in txs)
        recovery_rate_pct = (
            (recovered_amount_paise / total_amount_paise * 100)
            if total_amount_paise > 0 else 0.0
        )
        recovered_amt_str = f"₹{recovered_amount_paise / 100:,.2f}"

        if batch_id in _DEMO_BATCH_STATUS:
            _DEMO_BATCH_STATUS[batch_id]["status"] = "completed"
            _DEMO_BATCH_STATUS[batch_id]["percent"] = 100
            _DEMO_BATCH_STATUS[batch_id]["completed"] = len(txs)
            _DEMO_BATCH_STATUS[batch_id]["phase"] = "Completed"
            _DEMO_BATCH_STATUS[batch_id]["current_action"] = (
                f"✓ Demo completed! {confirmed_count} transactions confirmed recovered ({recovered_amt_str}), "
                f"{len(txs) - confirmed_count} awaiting confirmation."
            )
            _append_log(
                batch_id,
                "done",
                f"Demo batch {batch_id} complete: {confirmed_count}/{len(txs)} payments confirmed recovered "
                f"({recovered_amt_str}, {recovery_rate_pct:.1f}% value recovery rate).",
            )

        return {
            "batch_id": batch_id,
            "total_created": len(txs),
            "confirmed_recovered": confirmed_count,
            "amount_recovered_paise": recovered_amount_paise,
            "recovery_rate_pct": recovery_rate_pct,
        }
    except Exception as exc:
        logger.exception("Fatal error executing full demo batch %s: %s", batch_id, exc)
        if batch_id in _DEMO_BATCH_STATUS:
            _DEMO_BATCH_STATUS[batch_id]["status"] = "failed"
            _DEMO_BATCH_STATUS[batch_id]["phase"] = "Failed"
            _DEMO_BATCH_STATUS[batch_id]["current_action"] = f"Demo batch execution failed: {exc}"
            _append_log(batch_id, "error", f"Fatal batch error: {exc}")
        raise
