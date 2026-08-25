// src/pages/Dashboard.jsx — Screen 1: overview metrics + transaction list
import { useEffect, useState } from "react";
import { api } from "../api";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge, CategoryBadge } from "../components/StatusBadge";

function fmt(paise) {
  return "₹" + (paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function Dashboard({ setPage, setSelectedTx }) {
  const [metrics, setMetrics] = useState(null);
  const [txs, setTxs] = useState([]);
  const [batches, setBatches] = useState([]);
  const [selectedBatch, setSelectedBatch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Demo Runner state
  const [isDemoRunning, setIsDemoRunning] = useState(false);
  const [demoProgress, setDemoProgress] = useState(null);
  const [demoBanner, setDemoBanner] = useState("");

  async function loadData(batchId = selectedBatch) {
    setLoading(true);
    setError("");
    try {
      const [m, t, bList] = await Promise.all([
        api.getSummary(batchId || null),
        api.listTransactions(50, 0, batchId || null),
        api.listBatches().catch(() => []),
      ]);
      setMetrics(m);
      setTxs(t.items || []);
      setBatches(bList || []);
    } catch (e) {
      setError("Could not reach the backend. Is the server running on port 8000?");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData(selectedBatch);
  }, [selectedBatch]);

  async function handleRunDemo() {
    if (isDemoRunning) return;
    setIsDemoRunning(true);
    setDemoBanner("");
    setDemoProgress({ completed: 0, total: 10, percent: 0, status: "running", phase: "Initializing", current_action: "Starting demo batch runner...", logs: [] });

    const startTime = Date.now();
    const TIMEOUT_MS = 180000; // 3-minute safety net

    try {
      const initResp = await api.runDemoBatch();
      const batchId = initResp.batch_id;

      // Poll every 2 seconds
      const pollTimer = setInterval(async () => {
        try {
          // Safety timeout check
          if (Date.now() - startTime > TIMEOUT_MS) {
            clearInterval(pollTimer);
            setIsDemoRunning(false);
            setDemoBanner("⚠ Demo batch is taking longer than expected (~3 mins elapsed). Please check server logs.");
            await loadData();
            return;
          }

          const statusResp = await api.getDemoStatus(batchId);
          setDemoProgress(statusResp);

          if (statusResp.status === "completed" || (statusResp.total > 0 && statusResp.completed >= statusResp.total)) {
            clearInterval(pollTimer);
            setIsDemoRunning(false);
            setDemoBanner(`✓ Demo batch ${batchId} completed successfully! Displaying results below.`);
            setSelectedBatch(batchId);
            await loadData(batchId);
          } else if (statusResp.status === "failed") {
            clearInterval(pollTimer);
            setIsDemoRunning(false);
            setDemoBanner(`❌ Demo batch failed: ${statusResp.current_action || "Encountered an execution error."}`);
            setSelectedBatch(batchId);
            await loadData(batchId);
          }
        } catch {
          // If polling fails temporarily (network jitter), keep polling until timeout
        }
      }, 2000);
    } catch (err) {
      setIsDemoRunning(false);
      setDemoProgress(null);
      setError(`Failed to trigger demo batch: ${err.message}`);
    }
  }

  function handleBatchChange(e) {
    const val = e.target.value;
    setSelectedBatch(val);
  }

  function openTx(tx) {
    setSelectedTx(tx);
    setPage("transaction");
  }

  if (error) return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="bg-red-50 border border-red-300 text-red-700 rounded-xl p-6 flex gap-3 items-start">
        <span className="text-xl">⚠</span>
        <div>
          <p className="font-semibold">Backend not reachable</p>
          <p className="text-sm mt-1">{error}</p>
          <p className="text-sm mt-2 font-mono bg-red-100 inline-block px-2 py-1 rounded">
            uvicorn app.main:app --reload
          </p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Recovery Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            AI-powered payment failure recovery · Razorpay Test Mode
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Run Demo Batch Button */}
          <button
            onClick={handleRunDemo}
            disabled={isDemoRunning}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold shadow-sm transition-all ${
              isDemoRunning
                ? "bg-purple-100 text-purple-700 cursor-not-allowed border border-purple-300"
                : "bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white"
            }`}
          >
            {isDemoRunning ? (
              <>
                <svg className="animate-spin h-4 w-4 text-purple-700" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                </svg>
                <span>Running Demo Batch…</span>
              </>
            ) : (
              <>
                <span>🚀</span>
                <span>Run Demo Batch</span>
              </>
            )}
          </button>

          {/* Batch Selector */}
          <div className="flex items-center gap-2 bg-white border border-gray-300 rounded-lg px-3 py-1.5 shadow-sm text-sm">
            <span className="text-gray-500 font-medium text-xs">Scope:</span>
            <select
              value={selectedBatch}
              onChange={handleBatchChange}
              className="bg-transparent text-gray-800 font-medium text-xs focus:outline-none cursor-pointer"
            >
              <option value="">All Time (Cumulative)</option>
              {batches.map((b) => (
                <option key={b.batch_id} value={b.batch_id}>
                  {b.batch_id} ({b.count} txs)
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => loadData(selectedBatch)}
            disabled={isDemoRunning}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300 rounded-lg text-xs font-medium transition-colors shadow-sm"
          >
            <span>↻</span> Refresh
          </button>
        </div>
      </div>

      {/* Demo Explanatory Note & Live Progress Banner */}
      <div className="bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-100 rounded-xl p-4 text-xs text-indigo-900 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <span className="text-base mt-0.5">ℹ️</span>
            <div>
              <p className="font-semibold text-indigo-950">Interactive Demo Runner for Evaluators</p>
              <p className="text-indigo-800 mt-0.5 leading-relaxed">
                Creates 10 synthetic failed transactions across all root-cause categories, runs the live recovery pipeline against Razorpay test-mode APIs, and simulates payment confirmation via webhook. Takes about a minute.
              </p>
            </div>
          </div>
        </div>

        {/* Live Progress Bar & Action Stream when running */}
        {isDemoRunning && demoProgress && (
          <div className="mt-4 pt-3 border-t border-indigo-200/60 space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold text-indigo-900">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-200 text-indigo-950">
                  {demoProgress.phase || "Processing"}
                </span>
                <span>{demoProgress.completed} / {demoProgress.total} processed</span>
              </div>
              <span className="font-mono">{demoProgress.percent}%</span>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-indigo-200/80 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${Math.max(demoProgress.percent, 8)}%` }}
              ></div>
            </div>

            {/* Current Active Step */}
            {demoProgress.current_action && (
              <div className="bg-white/80 border border-indigo-200 rounded-lg px-3 py-2 text-xs flex items-center gap-2">
                <span className="animate-pulse flex h-2 w-2 rounded-full bg-indigo-600"></span>
                <span className="font-medium text-indigo-950 truncate">
                  {demoProgress.current_action}
                </span>
              </div>
            )}

            {/* Live Activity Stream Console */}
            {demoProgress.logs && demoProgress.logs.length > 0 && (
              <div className="bg-gray-900 text-gray-200 rounded-lg p-3 font-mono text-[11px] max-h-48 overflow-y-auto shadow-inner space-y-1.5 flex flex-col-reverse">
                {[...demoProgress.logs].reverse().map((log, idx) => (
                  <div key={idx} className="flex items-start gap-2 leading-relaxed">
                    <span className="text-gray-500 shrink-0 select-none">[{log.time}]</span>
                    <span className="shrink-0">
                      {log.type === "classify" && "🤖"}
                      {log.type === "order" && "💳"}
                      {log.type === "link" && "🔗"}
                      {log.type === "webhook" && "✓"}
                      {log.type === "escalate" && "🛡"}
                      {log.type === "error" && "⚠"}
                      {log.type === "init" && "📦"}
                      {log.type === "done" && "🏁"}
                    </span>
                    <span className={
                      log.type === "webhook" || log.type === "done"
                        ? "text-emerald-400 font-semibold"
                        : log.type === "order" || log.type === "link"
                        ? "text-cyan-300"
                        : log.type === "escalate"
                        ? "text-amber-300"
                        : log.type === "error"
                        ? "text-rose-400"
                        : "text-gray-200"
                    }>
                      {log.message}
                      {log.detail && (
                        <span className="text-indigo-300 ml-1.5 opacity-80 text-[10px]">
                          ({log.detail})
                        </span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Completion Banner with Log summary preview */}
        {demoBanner && !isDemoRunning && (
          <div className="mt-3 pt-2.5 border-t border-indigo-200/60 font-medium text-emerald-800 space-y-2">
            <div className="flex items-center gap-1.5">
              <span>{demoBanner}</span>
            </div>
            {demoProgress?.logs && demoProgress.logs.length > 0 && (
              <details className="text-[11px] text-gray-600 font-normal cursor-pointer">
                <summary className="font-medium text-indigo-700 hover:text-indigo-900">
                  View Full Live Execution Log ({demoProgress.logs.length} events)
                </summary>
                <div className="bg-gray-900 text-gray-200 rounded-lg p-3 font-mono mt-2 max-h-48 overflow-y-auto shadow-inner space-y-1.5">
                  {demoProgress.logs.map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 leading-relaxed">
                      <span className="text-gray-500 shrink-0">[{log.time}]</span>
                      <span>{log.message}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      {/* Metric cards */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            label="Confirmed Recovered"
            value={fmt(metrics.amount_recovered_paise || 0)}
            sub={`${metrics.by_status?.recovered || 0} confirmed via webhook`}
            accent="green"
          />
          <MetricCard
            label="Recovery Rate"
            value={`${(metrics.recovery_rate_pct || 0).toFixed(1)}%`}
            sub="confirmed / attempted"
            accent="blue"
          />
          <MetricCard
            label="Awaiting Confirmation"
            value={fmt(metrics.amount_pending_confirmation_paise || 0)}
            sub={`${metrics.by_status?.pending_confirmation || 0} initiated/link sent`}
            accent="yellow"
          />
          <MetricCard
            label="Escalated"
            value={metrics.by_status?.escalated || 0}
            sub="manual review needed"
            accent="red"
          />
        </div>
      )}

      {/* Transactions table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-700">
            All Transactions
            {!loading && <span className="ml-2 text-gray-400 font-normal text-sm">({txs.length})</span>}
          </h2>
          <span className="text-xs text-gray-400">Click any row to view details & run recovery</span>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading transactions…</div>
        ) : txs.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <p className="text-4xl">📭</p>
            <p className="text-gray-500 font-medium">No transactions yet</p>
            <p className="text-gray-400 text-sm">
              Run the demo script to generate some:
            </p>
            <code className="bg-gray-100 px-3 py-1.5 rounded text-sm block w-max mx-auto">
              python scripts/demo_run.py
            </code>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 uppercase text-xs tracking-wider">
                <tr>
                  <th className="px-6 py-3 text-left">Payment ID</th>
                  <th className="px-6 py-3 text-right">Amount</th>
                  <th className="px-6 py-3 text-left">Status</th>
                  <th className="px-6 py-3 text-left">Category</th>
                  <th className="px-6 py-3 text-left">Error Code</th>
                  <th className="px-6 py-3 text-left">Retries</th>
                  <th className="px-6 py-3 text-left">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {txs.map((tx) => (
                  <tr
                    key={tx.id}
                    onClick={() => openTx(tx)}
                    className="hover:bg-blue-50 cursor-pointer transition-colors"
                  >
                    <td className="px-6 py-3 font-mono text-xs text-blue-700">
                      {tx.razorpay_payment_id}
                    </td>
                    <td className="px-6 py-3 text-right font-semibold text-gray-700">
                      {fmt(tx.amount)}
                    </td>
                    <td className="px-6 py-3">
                      <StatusBadge status={tx.status} />
                    </td>
                    <td className="px-6 py-3">
                      <CategoryBadge category={tx.root_cause_category} />
                    </td>
                    <td className="px-6 py-3 font-mono text-xs text-gray-500">
                      {tx.failure_reason_code || "—"}
                    </td>
                    <td className="px-6 py-3 text-center text-gray-600">
                      {tx.retry_count}
                    </td>
                    <td className="px-6 py-3 text-gray-400 text-xs">
                      {new Date(tx.created_at).toLocaleString("en-IN")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
