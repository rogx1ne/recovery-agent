# ⚡ Razorpay AI Revenue Recovery Agent

> **Razorpay AI Buildathon Submission** | **Track 03: AI Revenue Recovery**  
> An autonomous revenue recovery system that detects failed payments, classifies root causes using Groq AI (`openai/gpt-oss-20b`), executes bounded recovery workflows, and tracks every decision in a human-readable audit trail.

---

## 📊 Measured Revenue Recovery Performance

> *"Don't just identify the problem. Show measured money recovered across a batch, with compliant escalation, stopping rules, and an audit trail."* — **Razorpay Track 03 Bar**

<!-- Measured across a single batch of 10 transactions (DEMO_BATCH) scoped via batch_id with simulated webhook confirmations -->
*Figures below are scoped to a single 10-transaction batch via `batch_id` (not cumulative across all runs), verified with simulated Razorpay webhook payment confirmations:*

| Metric | Measured Value |
|---|---|
| **Total At-Risk Revenue** | **₹8,947.00 (10 transactions)** |
| **Confirmed Recovered (Webhook)** | **₹5,250.00 (5 transactions)** |
| **Awaiting Confirmation (`retry_initiated` / `link_sent`)** | **₹3,697.00 (5 transactions)** |
| **Escalated (Manual Review)** | **₹0.00 (0 transactions)** |
| **Confirmed Count Recovery Rate** | **50.0% (5 / 10 transactions)** |
| **Confirmed Value Recovery Rate** | **58.7% (₹5,250.00 / ₹8,947.00)** |

---

## 🌟 Key Features

1. **🤖 Groq AI Root Cause Classification (`openai/gpt-oss-20b`)**
   - Analyzes raw Razorpay error codes (`card_declined`, `do_not_honour`, `mandate_failed`, `3ds_failed`) alongside transaction metadata.
   - Categorizes failures into 5 normalized buckets and generates a 2-sentence plain-English business explanation for audit logs.
   - High-throughput free tier (14,400 requests/day) with ultra-low latency inference.

2. **💬 Conversational Hinglish Customer Messaging**
   - Automatically generates empathetic, high-converting **Hinglish WhatsApp / SMS messages** personalized for each customer and failure type.
   - Includes one-click copy buttons in the UI for merchant support teams.

3. **👑 VIP High-Value Handling (≥ ₹10,000)**
   - Automatically flags transactions $\ge$ ₹10,000 INR for VIP priority processing and human-in-the-loop escalation tags to minimize high-value customer churn.

4. **🔒 Hard Stopping Rules & Bounded Escalation**
   - Hard-capped retry counts (max 1 or 2 attempts) to prevent infinite loops, card lockouts, or bank fraud flagging.
   - Escalates gracefully to `ESCALATED` status when retries are exhausted or link creation fails.

5. **🪝 Full Webhook Loop-Closing**
   - Receives Razorpay `payment.captured` and `payment_link.paid` webhooks with **HMAC-SHA256 signature verification**.
   - Automatically updates status to `RECOVERED` when customer payment completes.

6. **💻 Modern React Dashboard**
   - Built with **React 18 + Vite + Tailwind CSS**.
   - Features real-time metric cards, searchable transactions, single-click recovery execution, and step-by-step AI audit timelines.

---

## 🏗️ Architecture & 5-Stage Pipeline

```text
Customer Checkout Failure 
          │
          ▼
   ┌──────────────┐
   │ 1. DETECTED  │ ──► Reads failure code & amount into DB
   └──────────────┘
          │
          ▼
   ┌──────────────┐
   │ 2. CLASSIFIED│ ──► Groq AI determines category & plain-English reasoning
   └──────────────┘
          │
          ▼
   ┌──────────────┐
   │ 3. DECIDED   │ ──► Policy table selects bounded action (Retry / Link / Escalate)
   └──────────────┘
          │
          ▼
   ┌──────────────┐
   │ 4. EXECUTED  │ ──► Razorpay API call (Order created / Payment link + Hinglish msg)
   └──────────────┘
          │
          ▼
   ┌──────────────┐
   │ 5. OUTCOME   │ ──► Marks RECOVERED or ESCALATED with complete Audit Log entry
   └──────────────┘
```

---

## 📋 Recovery Policy Table

| Root-Cause Category | Automated Action | Max Retries | Retry Delay | Business Rationale |
|---|---|---|---|---|
| `card_declined` | `retry_then_link` | 1 retry | 5 sec | Retry once for transient bank rejection. If it fails, send link so customer can switch cards. |
| `insufficient_fund` | `payment_link` | 0 retries | Immediate | Retrying won't help. Send link with Hinglish message so customer can pay when funds arrive. |
| `gateway_technical_error` | `immediate_retry` | 2 retries | 2 sec | Transient gateway blip. Retry up to 2 times. If both fail, escalate to avoid loop. |
| `authentication_failed` | `payment_link` | 0 retries | Immediate | 3DS / OTP failed. Auto-retry would fail again. Send link for customer manual auth. |
| `subscription_failed` | `immediate_retry` | 2 retries | 10 sec | Recurring mandate failure. Short retry window. Escalate if unrecovered. |
| `unknown` | `payment_link` | 0 retries | Immediate | Safe fallback: issue link, do not auto-retry unclassified errors. |

---

## 📁 Repository Structure

```text
recovery-agent/
├── app/
│   ├── main.py                     # FastAPI entrypoint & middleware
│   ├── config.py                   # Pydantic environment configuration
│   ├── db.py                       # SQLAlchemy SQLite setup & session manager
│   ├── models/
│   │   ├── transaction.py          # Transaction ORM model & RootCauseCategory enum
│   │   └── audit_log.py            # AuditLog ORM model & AuditStep enum
│   ├── schemas/
│   │   ├── transaction.py          # Request / Response Pydantic schemas
│   │   └── audit_log.py            # AuditLog schemas
│   ├── services/
│   │   ├── razorpay_client.py      # Razorpay SDK Python wrapper (Test Mode)
│   │   ├── classifier.py           # Substring fallback rule lookup table
│   │   ├── llm_classifier.py       # Groq AI classification & Hinglish messaging
│   │   ├── decision_policy.py      # Policy table, VIP thresholds, retry gates
│   │   └── executor.py             # 5-stage recovery pipeline orchestrator
│   └── routers/
│       ├── transactions.py         # Transaction CRUD API
│       ├── recovery.py             # Pipeline trigger API
│       ├── audit.py                # Audit log search & filtering API
│       ├── stats.py                # Dashboard recovery statistics API
│       └── webhooks.py             # Razorpay HMAC signature webhook receiver
├── frontend/                       # React 18 + Vite + Tailwind CSS UI
│   ├── src/
│   │   ├── api.js                  # Centralized API client
│   │   ├── pages/                  # Dashboard, Transactions, Detail & AuditLog pages
│   │   └── components/             # Status badges, Metric cards & Navbar
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── check_razorpay_setup.py     # Startup sanity check for Razorpay API connectivity
│   ├── generate_batch.py           # Synthetic failed transaction batch generator
│   ├── run_batch_recovery.py       # Batch pipeline execution runner
│   └── demo_run.py                 # Live colorized end-to-end demo script
├── tests/
│   ├── test_api.py                 # Integration tests (FastAPI TestClient)
│   ├── test_classifier.py          # Classification unit tests
│   └── test_decision_policy.py     # Decision policy & retry cap tests
├── requirements.txt
└── README.md
```

---

## 🚀 Quickstart Guide

### Prerequisites
- **Python 3.10+** (Python 3.14 fully supported)
- **Node.js 18+** & **npm**

### 1. Backend Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/razorpay-recovery-agent.git
cd recovery-agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure Environment
cp .env.example .env

# Verify Razorpay API connectivity (Startup Sanity Check)
python scripts/check_razorpay_setup.py
```

*(Optional)* Edit `.env` to add your free **Groq API Key** (`GROQ_API_KEY=gsk_...` from https://console.groq.com/keys) for high-speed AI classification and Hinglish recovery messaging.

```bash
# Start FastAPI Server
uvicorn app.main:app --reload --port 8000
```
FastAPI Swagger docs will be available at: `http://localhost:8000/docs`

---

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser to view the React Dashboard.

---

### 3. Run End-to-End Batch Recovery Demo

With the backend running, open a new terminal and run:

```bash
python scripts/demo_run.py
```

This will automatically:
1. Register **10 failed transactions** across all 5 failure categories.
2. Run the recovery pipeline on each transaction.
3. Output a colorized before/after recovery summary with exact rupee amounts and AI audit trails.

---

## 🧪 Testing

The codebase includes comprehensive unit and integration test coverage (**60 passing tests**).

```bash
pytest tests/ -v
```

---

## 📡 API Reference Summary

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/transactions/` | `POST` | Register a new failed transaction |
| `/api/v1/transactions/` | `GET` | List transactions with pagination & filters |
| `/api/v1/recovery/{id}` | `POST` | Trigger 5-stage automated recovery pipeline |
| `/api/v1/audit/transaction/{id}` | `GET` | Retrieve complete 5-step AI audit trail |
| `/api/v1/stats/summary` | `GET` | Overall recovery rate, ₹ recovered & count stats |
| `/api/v1/stats/by-category` | `GET` | Recovery metrics breakdown per category |
| `/api/v1/webhooks/razorpay` | `POST` | Razorpay webhook handler for payment capture |

---

## ⚖️ Compliance & Safety
- **Defensive Design:** Automated actions are strictly bounded by deterministic policy caps.
- **HMAC Verification:** Webhook endpoints verify Razorpay signatures.
- **Test Mode Isolated:** Uses standard Razorpay Test Mode keys (`rzp_test_...`).
