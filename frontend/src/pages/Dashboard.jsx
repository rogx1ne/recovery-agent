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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [m, t] = await Promise.all([api.getSummary(), api.listTransactions(50)]);
      setMetrics(m);
      setTxs(t.items || []);
    } catch (e) {
      setError("Could not reach the backend. Is the server running on port 8000?");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

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
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Recovery Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            AI-powered payment failure recovery · Razorpay Test Mode
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <span>↻</span> Refresh
        </button>
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
