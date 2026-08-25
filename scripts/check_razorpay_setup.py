#!/usr/bin/env python3
"""
scripts/check_razorpay_setup.py — Startup Sanity Check for Razorpay APIs.

Tests Razorpay API connectivity and configuration for the two core products
the Recovery Agent depends on:
  1. Orders API (used for automated retries)
  2. Payment Links API (used for customer self-serve recovery)

Run standalone before running demos:
  python scripts/check_razorpay_setup.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.services import razorpay_client

# ANSI colors
GREEN = lambda s: f"\033[92m{s}\033[0m"
RED = lambda s: f"\033[91m{s}\033[0m"
YELLOW = lambda s: f"\033[93m{s}\033[0m"
CYAN = lambda s: f"\033[96m{s}\033[0m"
BOLD = lambda s: f"\033[1m{s}\033[0m"


def main() -> int:
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print()
    print(BOLD("═══════════════════════════════════════════════════════════════"))
    print(BOLD("  🔍  Razorpay Setup & API Connectivity Sanity Check"))
    print(BOLD("═══════════════════════════════════════════════════════════════"))
    print(f"  Key ID:     {CYAN(settings.razorpay_key_id)}")
    print(f"  App Env:    {settings.app_env}")
    print()

    has_errors = False

    # ── Test 1: Order Creation (for retries) ──────────────────────────────────
    print(f"  [1/2] Testing {BOLD('order.create()')} (₹1.00 retry order)...")
    try:
        order = razorpay_client.create_order_for_retry(
            amount=100,  # ₹1.00 = 100 paise
            currency="INR",
            receipt=f"sanity_order_{ts}",
            notes={"purpose": "sanity_check", "created_at": ts},
        )
        order_id = order.get("id", "N/A")
        print(f"        {GREEN('✓ OK')} — Order created successfully: {BOLD(order_id)}")
    except Exception as exc:
        has_errors = True
        print(f"        {RED('✗ FAILED')} — {exc}")

    print()

    # ── Test 2: Payment Link Creation ─────────────────────────────────────────
    print(f"  [2/2] Testing {BOLD('payment_link.create()')} (₹1.00 recovery link with valid customer contact)...")
    try:
        link = razorpay_client.create_payment_link(
            amount=100,  # ₹1.00 = 100 paise
            currency="INR",
            description=f"Sanity Check Link ({ts})",
            customer_contact="+919876543210",
            customer_email="test.recovery@example.com",
            customer_name="Test Customer",
            reference_id=f"sanity_link_{ts}",
            expire_minutes=30,
        )
        link_id = link.get("id", "N/A")
        link_url = link.get("short_url", "N/A")
        print(f"        {GREEN('✓ OK')} — Link created successfully:")
        print(f"             ID:  {BOLD(link_id)}")
        print(f"             URL: {CYAN(link_url)}")
    except Exception as exc:
        has_errors = True
        print(f"        {RED('✗ FAILED')} — {exc}")

    print()
    print(BOLD("═══════════════════════════════════════════════════════════════"))
    if has_errors:
        print(f"  {RED(BOLD('STATUS: SANITY CHECK FAILED'))}")
        print(f"  {YELLOW('Note: See exact error details above.')}")
        print(BOLD("═══════════════════════════════════════════════════════════════\n"))
        return 1
    else:
        print(f"  {GREEN(BOLD('STATUS: ALL SYSTEMS OPERATIONAL'))}")
        print(f"  {CYAN('Test orders & links in test mode are harmless and require no settlement.')}")
        print(BOLD("═══════════════════════════════════════════════════════════════\n"))
        return 0


if __name__ == "__main__":
    sys.exit(main())
