"""
tests/test_api.py — Integration tests for the FastAPI endpoints.
Uses FastAPI's TestClient with an in-memory SQLite database so no server
needs to be running and no real Razorpay calls are made.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock

# ─── Test database (in-memory SQLite, shared connection) ─────────────────────
# We use a module-scoped shared engine so all in-memory tables persist for the
# duration of the test module.

TEST_DATABASE_URL = "sqlite:///./test_recovery_agent.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """
    Patch app.db.engine with the test engine so that init_db() (called via
    lifespan) creates tables on our test database, then override get_db so
    all request sessions also use it.
    LLM classifier is disabled so tests don't require a Gemini API key.
    """
    import app.db as app_db
    import app.config as app_config
    from app.main import app
    from app.db import get_db

    # Swap the real engine for the test engine
    original_engine = app_db.engine
    app_db.engine = test_engine

    # Also patch the SessionLocal bound to the real engine
    original_session = app_db.SessionLocal
    app_db.SessionLocal = TestingSessionLocal

    # Disable LLM so tests are fully deterministic (no API key needed)
    import os
    os.environ["USE_LLM_CLASSIFIER"] = "false"
    app_config.get_settings.cache_clear()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
    # Tear down tables and restore originals
    from app.db import Base
    Base.metadata.drop_all(bind=test_engine)
    app_db.engine = original_engine
    app_db.SessionLocal = original_session
    del os.environ["USE_LLM_CLASSIFIER"]
    app_config.get_settings.cache_clear()


@pytest.fixture(scope="module")
def sample_tx(client):
    """
    Create a single failed transaction and return its JSON response.
    Module-scoped so it runs once — avoids 409 on duplicate payment ID
    when the fixture is requested by multiple tests in the same module.
    """
    resp = client.post("/api/v1/transactions/", json={
        "razorpay_payment_id": "pay_IntegTest_SampleTx",
        "amount": 50000,
        "currency": "INR",
        "status": "failed",
        "failure_reason_code": "card_declined",
    })
    assert resp.status_code == 201
    return resp.json()


# ─── Health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200


# ─── Transactions ─────────────────────────────────────────────────────────────

class TestTransactions:
    def test_create_transaction(self, client):
        r = client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_CreateTest001",
            "amount": 10000,
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": "insufficient_funds",
        })
        assert r.status_code == 201
        body = r.json()
        assert body["razorpay_payment_id"] == "pay_CreateTest001"
        assert body["status"] == "failed"

    def test_duplicate_payment_id_returns_409(self, client, sample_tx):
        r = client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": sample_tx["razorpay_payment_id"],
            "amount": 1000,
            "currency": "INR",
            "status": "failed",
        })
        assert r.status_code == 409

    def test_list_transactions(self, client):
        r = client.get("/api/v1/transactions/")
        assert r.status_code == 200
        body = r.json()
        assert "total" in body
        assert isinstance(body["items"], list)

    def test_get_transaction(self, client, sample_tx):
        tx_id = sample_tx["id"]
        r = client.get(f"/api/v1/transactions/{tx_id}")
        assert r.status_code == 200
        assert r.json()["id"] == tx_id

    def test_get_nonexistent_transaction_returns_404(self, client):
        r = client.get("/api/v1/transactions/99999")
        assert r.status_code == 404


# ─── Recovery ─────────────────────────────────────────────────────────────────

class TestRecovery:
    def test_trigger_recovery_card_declined(self, client):
        # Create a fresh transaction for this test
        create_resp = client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_RecoveryTest_CardDecline",
            "amount": 25000,
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": "card_declined",
        })
        tx_id = create_resp.json()["id"]

        # Mock the Razorpay API calls so we don't need real credentials
        mock_order = {"id": "order_MockOrderId001", "status": "created", "amount": 25000}
        with patch("app.services.razorpay_client.create_order_for_retry", return_value=mock_order):
            r = client.post(f"/api/v1/recovery/{tx_id}")

        assert r.status_code == 200
        body = r.json()
        assert body["transaction_id"] == tx_id
        assert body["final_status"] in ("retry_initiated", "escalated")  # depends on mock
        assert "steps_taken" in body
        assert "detected" in body["steps_taken"]

    def test_recovery_unknown_transaction_returns_404(self, client):
        r = client.post("/api/v1/recovery/99999")
        assert r.status_code == 404

    def test_recovery_already_recovered_returns_409(self, client):
        # Create and recover a transaction
        create_resp = client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_RecoveryTest_AlreadyDone",
            "amount": 5000,
            "currency": "INR",
            "status": "recovered",
        })
        tx_id = create_resp.json()["id"]
        r = client.post(f"/api/v1/recovery/{tx_id}")
        assert r.status_code == 409

    def test_insufficient_funds_recovery_sends_link(self, client):
        create_resp = client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_RecoveryTest_Insuff",
            "amount": 100000,
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": "insufficient_funds",
            "customer_contact": "+919876543210",
            "customer_email": "customer@example.com",
            "customer_name": "Test Customer",
        })
        tx_id = create_resp.json()["id"]

        mock_link = {
            "id": "plink_MockLinkId001",
            "short_url": "https://rzp.io/i/mock123",
            "status": "created",
        }
        with patch("app.services.razorpay_client.create_payment_link", return_value=mock_link):
            r = client.post(f"/api/v1/recovery/{tx_id}")

        assert r.status_code == 200
        body = r.json()
        assert body["final_status"] == "link_sent"
        assert body["artefacts"].get("payment_link_url") == "https://rzp.io/i/mock123"

    def test_payment_link_missing_contact_escalates_cleanly(self, client):
        create_resp = client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_RecoveryTest_NoContact",
            "amount": 100000,
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": "insufficient_funds",
            # No customer_contact or customer_email
        })
        tx_id = create_resp.json()["id"]

        r = client.post(f"/api/v1/recovery/{tx_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["final_status"] == "escalated"
        assert "no customer contact" in body["artefacts"].get("payment_link_error", "").lower()


# ─── Audit ────────────────────────────────────────────────────────────────────

class TestAudit:
    def test_list_audit_logs(self, client):
        r = client.get("/api/v1/audit/")
        assert r.status_code == 200
        assert "total" in r.json()

    def test_audit_trail_for_transaction(self, client):
        # First create and recover a transaction to generate audit logs
        create_resp = client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_AuditTrailTest001",
            "amount": 30000,
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": "gateway_technical_error",
        })
        tx_id = create_resp.json()["id"]

        mock_order = {"id": "order_AuditMock001", "status": "created", "amount": 30000}
        with patch("app.services.razorpay_client.create_order_for_retry", return_value=mock_order):
            client.post(f"/api/v1/recovery/{tx_id}")

        audit_resp = client.get(f"/api/v1/audit/transaction/{tx_id}")
        assert audit_resp.status_code == 200
        logs = audit_resp.json()["items"]
        assert len(logs) >= 5  # at least 5 pipeline steps
        steps = [log["step"] for log in logs]
        assert "detected" in steps
        assert "classified" in steps
        assert "decided" in steps
        assert "executed" in steps
        assert "outcome" in steps

    def test_audit_logs_have_reasoning(self, client):
        r = client.get("/api/v1/audit/?limit=10")
        assert r.status_code == 200
        for log in r.json()["items"]:
            assert len(log.get("reasoning", "")) > 0, f"Log {log['id']} has empty reasoning"


# ─── Metrics ──────────────────────────────────────────────────────────────────

class TestMetrics:
    def test_summary_returns_expected_keys(self, client):
        r = client.get("/api/v1/stats/summary")
        assert r.status_code == 200
        body = r.json()
        assert "total_transactions" in body
        assert "recovery_rate_pct" in body
        assert "by_status" in body
        assert "amount_recovered_inr" in body

    def test_by_category_returns_dict(self, client):
        r = client.get("/api/v1/stats/by-category")
        assert r.status_code == 200
        assert "categories" in r.json()

    def test_summary_and_category_scoped_by_batch_id(self, client):
        # Create transactions with two different batch_ids
        client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_Batch1_Tx1",
            "amount": 10000,
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": "card_declined",
            "batch_id": "test_batch_alpha",
        })
        client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_Batch1_Tx2",
            "amount": 20000,
            "currency": "INR",
            "status": "recovered",
            "failure_reason_code": "card_declined",
            "batch_id": "test_batch_alpha",
        })
        client.post("/api/v1/transactions/", json={
            "razorpay_payment_id": "pay_Batch2_Tx1",
            "amount": 50000,
            "currency": "INR",
            "status": "failed",
            "failure_reason_code": "network_error",
            "batch_id": "test_batch_beta",
        })

        # Test batch_alpha scoped summary
        r_alpha = client.get("/api/v1/stats/summary?batch_id=test_batch_alpha")
        assert r_alpha.status_code == 200
        alpha_body = r_alpha.json()
        assert alpha_body["batch_id"] == "test_batch_alpha"
        assert alpha_body["total_transactions"] == 2
        assert alpha_body["by_status"]["recovered"] == 1
        assert alpha_body["by_status"]["failed"] == 1
        assert alpha_body["amount_recovered_inr"] == 200.0

        # Test batch_beta scoped summary
        r_beta = client.get("/api/v1/stats/summary?batch_id=test_batch_beta")
        assert r_beta.status_code == 200
        beta_body = r_beta.json()
        assert beta_body["batch_id"] == "test_batch_beta"
        assert beta_body["total_transactions"] == 1
        assert beta_body["amount_recovered_inr"] == 0.0

        # Test list batches endpoint
        r_batches = client.get("/api/v1/stats/batches")
        assert r_batches.status_code == 200
        batch_ids = [b["batch_id"] for b in r_batches.json()]
        assert "test_batch_alpha" in batch_ids
        assert "test_batch_beta" in batch_ids


# ─── Webhooks ─────────────────────────────────────────────────────────────────

class TestWebhooks:
    """Webhook handler — verifies loop-closing without a real Razorpay signature."""

    def test_webhook_unhandled_event_returns_200(self, client):
        """Unknown event types must be acknowledged (Razorpay expects 200)."""
        r = client.post(
            "/api/v1/webhooks/razorpay",
            json={"event": "order.paid", "payload": {}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["acknowledged"] is True
        assert body["action"] == "ignored"

    def test_webhook_payment_captured_marks_recovered(self, client, sample_tx):
        """payment.captured should mark the matching transaction RECOVERED."""
        tx_id = sample_tx["id"]
        payment_id = sample_tx["razorpay_payment_id"]

        # Run recovery first so the transaction is in a non-failed state
        client.post(f"/api/v1/recovery/{tx_id}", json={})

        # Simulate Razorpay firing payment.captured
        r = client.post(
            "/api/v1/webhooks/razorpay",
            json={
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment_id,
                            "notes": {"original_payment_id": payment_id},
                        }
                    }
                },
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["acknowledged"] is True
        # Either marked_recovered or already_recovered are valid
        assert body["action"] in ("marked_recovered", "already_recovered")

    def test_webhook_invalid_json_returns_400(self, client):
        """Non-JSON body must return 400."""
        r = client.post(
            "/api/v1/webhooks/razorpay",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code in (400, 422)


# ─── Demo Batch ───────────────────────────────────────────────────────────────

class TestDemoRouter:
    """Tests for the interactive frontend demo runner endpoints."""

    def test_run_demo_batch_initiates_task(self, client):
        r = client.post("/api/v1/demo/run-batch")
        assert r.status_code == 202
        body = r.json()
        assert "batch_id" in body
        assert body["status"] == "running"
        assert body["total"] == 10

    def test_get_demo_status_returns_progress(self, client):
        batch_id = "test_demo_status_batch"
        # Status for non-existent or fresh batch
        r = client.get(f"/api/v1/demo/status/{batch_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["batch_id"] == batch_id
        assert body["total"] == 10
        assert "completed" in body
        assert "percent" in body

    def test_demo_seed_creation_and_execution(self, client):
        from app.models.transaction import TransactionStatus
        from app.services.demo_seed import (
            DEMO_BATCH_CASES,
            create_demo_transactions,
            simulate_demo_webhooks,
        )
        db = TestingSessionLocal()
        try:
            batch_id = "test_seed_batch_001"
            txs = create_demo_transactions(db, batch_id)
            assert len(txs) == len(DEMO_BATCH_CASES)
            assert all(tx.batch_id == batch_id for tx in txs)
            assert all(tx.customer_contact is not None for tx in txs)

            # Test webhook simulation
            mock_results = [
                {"id": txs[0].id, "final_status": "retry_initiated"},
                {"id": txs[1].id, "final_status": "link_sent"},
            ]
            confirmed = simulate_demo_webhooks(db, mock_results)
            assert confirmed == 2
            assert txs[0].status == TransactionStatus.RECOVERED
            assert txs[1].status == TransactionStatus.RECOVERED
        finally:
            db.close()
