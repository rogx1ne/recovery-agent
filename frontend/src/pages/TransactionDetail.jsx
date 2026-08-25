// src/pages/TransactionDetail.jsx — Screen 2 + 3: detail view + recovery trigger + result
import { useState } from "react";
import { api } from "../api";
import { StatusBadge, CategoryBadge, StepBadge } from "../components/StatusBadge";

function fmt(paise) {
  return "₹" + (paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

const STEP_DESCRIPTIONS = {
  detected:   "Found a failed payment and confirmed its status in the database.",
  classified: "AI analysed the error code and determined the root cause category.",
  decided:    "Looked up the policy table to select the best recovery action.",
  executed:   "Called the Razorpay API to perform the action (retry or payment link).",
  outcome:    "Recorded the final result — recovered or escalated.",
};

export function TransactionDetail({ tx: initialTx, setPage }) {
  const [tx, setTx] = useState(initialTx);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [showAudit, setShowAudit] = useState(false);
  const [error, setError] = useState("");

  async function runRecovery() {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const res = await api.triggerRecovery(tx.id);
      setResult(res);
      // Reload transaction to get updated status
      const updated = await api.getTransaction(tx.id);
      setTx(updated);
      // Load audit trail
      const audit = await api.getAuditTrail(tx.id);
      setAuditLogs(audit.items || []);
      setShowAudit(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  async function loadAudit() {
    try {
      const audit = await api.getAuditTrail(tx.id);
      setAuditLogs(audit.items || []);
      setShowAudit(true);
    } catch (e) {
      setError(e.message);
    }
  }

  const canRecover = tx.status === "failed";
  const alreadyProcessed = ["recovered", "escalated"].includes(tx.status);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">

      {/* Back button */}
      <button
        onClick={() => setPage("dashboard")}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors"
      >
        ← Back to Dashboard
      </button>

      {/* Transaction card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-800">Transaction Detail</h2>
            <p className="font-mono text-blue-700 text-sm mt-1">{tx.razorpay_payment_id}</p>
          </div>
          <StatusBadge status={tx.status} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-6">
          <InfoRow label="Amount" value={fmt(tx.amount)} big />
          <InfoRow label="Currency" value={tx.currency} />
          <InfoRow label="Retry Count" value={tx.retry_count} />
          <InfoRow label="Error Code" value={tx.failure_reason_code || "—"} mono />
          <InfoRow label="Root Cause" value={<CategoryBadge category={tx.root_cause_category} />} />
          <InfoRow label="Created" value={new Date(tx.created_at).toLocaleString("en-IN")} />
        </div>
      </div>

      {/* Recovery action */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-700 mb-4">Recovery Action</h3>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {canRecover && (
          <button
            onClick={runRecovery}
            disabled={running}
            className="w-full flex items-center justify-center gap-3 py-4 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white font-bold rounded-xl text-lg shadow-md transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {running ? (
              <>
                <span className="animate-spin text-xl">⟳</span>
                <span>Running recovery pipeline…</span>
              </>
            ) : (
              <>
                <span className="text-xl">▶</span>
                <span>Run Recovery</span>
              </>
            )}
          </button>
        )}

        {alreadyProcessed && !result && (
          <div className="text-center py-6">
            <p className="text-gray-500 mb-3">
              This transaction has already been processed.
            </p>
            <button
              onClick={loadAudit}
              className="px-5 py-2 border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              View Audit Trail
            </button>
          </div>
        )}

        {/* Recovery Result */}
        {result && (
          <div className="mt-6 space-y-4">
            {/* Final status banner */}
            <div className={`rounded-xl p-5 flex items-center gap-4 ${
              result.final_status === "recovered"
                ? "bg-green-50 border border-green-200"
                : "bg-yellow-50 border border-yellow-200"
            }`}>
              <span className="text-4xl">
                {result.final_status === "recovered" ? "✅" : "⚠️"}
              </span>
              <div>
                <p className="font-bold text-lg capitalize text-gray-800">
                  {result.final_status}
                </p>
                <p className="text-sm text-gray-600">
                  {result.final_status === "recovered"
                    ? "The payment was successfully recovered."
                    : "All automated attempts exhausted — needs manual review."}
                </p>
              </div>
            </div>

            {/* Steps taken */}
            <div className="bg-gray-50 rounded-xl p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
                Pipeline Steps
              </p>
              <div className="flex flex-wrap gap-2 items-center">
                {(result.steps_taken || []).map((step, i) => (
                  <span key={step} className="flex items-center gap-2">
                    <StepBadge step={step} />
                    {i < result.steps_taken.length - 1 && (
                      <span className="text-gray-400 text-sm">→</span>
                    )}
                  </span>
                ))}
              </div>
            </div>

            {/* Artefacts */}
            {result.artefacts && Object.keys(result.artefacts).length > 0 && (
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-blue-600 mb-2">
                  Recovery Artefact
                </p>
                {result.artefacts.payment_link_url && (
                  <Artefact
                    icon="🔗"
                    label="Payment Link (share with customer)"
                    value={result.artefacts.payment_link_url}
                    isLink
                  />
                )}
                {result.artefacts.recovery_message && (
                  <div className="mt-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-emerald-800 flex items-center gap-1">
                        💬 WhatsApp / SMS Message (Conversational Hinglish)
                      </span>
                      <button
                        onClick={() => navigator.clipboard.writeText(result.artefacts.recovery_message)}
                        className="text-xs bg-emerald-600 text-white px-2 py-0.5 rounded hover:bg-emerald-700 transition-colors"
                      >
                        Copy Text
                      </button>
                    </div>
                    <p className="text-xs text-emerald-900 font-sans leading-relaxed">
                      "{result.artefacts.recovery_message}"
                    </p>
                  </div>
                )}
                {result.artefacts.retry_order_id && (
                  <Artefact
                    icon="🔄"
                    label="Retry Order ID"
                    value={result.artefacts.retry_order_id}
                  />
                )}
                {result.artefacts.retry_payment_link_url && (
                  <Artefact
                    icon="🔗"
                    label="Retry Payment Link"
                    value={result.artefacts.retry_payment_link_url}
                    isLink
                  />
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Audit Trail */}
      {showAudit && auditLogs.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="font-semibold text-gray-700 mb-5">
            AI Audit Trail
            <span className="ml-2 text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-normal">
              {auditLogs.length} steps
            </span>
          </h3>
          <div className="relative pl-6">
            {/* Vertical timeline line */}
            <div className="absolute left-2 top-2 bottom-2 w-px bg-gray-200" />

            <div className="space-y-5">
              {auditLogs.map((log, i) => (
                <div key={log.id} className="relative">
                  {/* Dot */}
                  <div className="absolute -left-[18px] top-1 w-3 h-3 rounded-full bg-blue-500 border-2 border-white shadow" />

                  <div className="bg-gray-50 rounded-xl p-4 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <StepBadge step={log.step} />
                      <span className="text-xs text-gray-400">
                        {new Date(log.timestamp).toLocaleTimeString("en-IN")}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-gray-700">{log.detail}</p>
                    <div className="bg-white border border-gray-100 rounded-lg p-3">
                      <p className="text-xs font-semibold text-gray-400 uppercase mb-1">
                        AI Reasoning
                      </p>
                      <p className="text-sm text-gray-600 leading-relaxed">{log.reasoning}</p>
                    </div>
                    {STEP_DESCRIPTIONS[log.step] && (
                      <p className="text-xs text-gray-400 italic">
                        {STEP_DESCRIPTIONS[log.step]}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value, big, mono }) {
  return (
    <div>
      <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">{label}</p>
      <p className={`${big ? "text-xl font-bold text-gray-800" : "text-gray-700"} ${mono ? "font-mono text-xs" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function Artefact({ icon, label, value, isLink }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <div className="flex items-start gap-3">
      <span className="text-lg">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-500 mb-0.5">{label}</p>
        <p className="font-mono text-sm text-blue-800 break-all">{value}</p>
        <div className="mt-1 flex gap-2">
          {isLink && (
            <a
              href={value}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:underline"
            >
              Open link →
            </a>
          )}
          <button onClick={copy} className="text-xs text-gray-400 hover:text-gray-600">
            {copied ? "✓ Copied!" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}
