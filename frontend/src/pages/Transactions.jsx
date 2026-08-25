// src/pages/Transactions.jsx — Screen: searchable transactions list
import { useEffect, useState } from "react";
import { api } from "../api";
import { StatusBadge, CategoryBadge } from "../components/StatusBadge";

function fmt(paise) {
  return "₹" + (paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function Transactions({ setPage, setSelectedTx }) {
  const [txs, setTxs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    api.listTransactions(100).then((r) => {
      setTxs(r.items || []);
      setLoading(false);
    });
  }, []);

  const filtered = txs.filter((tx) => {
    const matchStatus = filter === "all" || tx.status === filter;
    const matchSearch =
      !search ||
      tx.razorpay_payment_id.toLowerCase().includes(search.toLowerCase()) ||
      (tx.failure_reason_code || "").toLowerCase().includes(search.toLowerCase());
    return matchStatus && matchSearch;
  });

  function openTx(tx) {
    setSelectedTx(tx);
    setPage("transaction");
  }

  const statusCounts = txs.reduce((acc, tx) => {
    acc[tx.status] = (acc[tx.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">All Transactions</h1>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          placeholder="Search by payment ID or error code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-gray-300 rounded-lg px-4 py-2 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
          {["all", "failed", "recovered", "escalated", "pending"].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize ${
                filter === s
                  ? "bg-white shadow text-gray-800"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {s} {statusCounts[s] ? `(${statusCounts[s]})` : ""}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-gray-400">No transactions match your filter.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 uppercase text-xs tracking-wider">
                <tr>
                  <th className="px-6 py-3 text-left">ID</th>
                  <th className="px-6 py-3 text-left">Payment ID</th>
                  <th className="px-6 py-3 text-right">Amount</th>
                  <th className="px-6 py-3 text-left">Status</th>
                  <th className="px-6 py-3 text-left">Category</th>
                  <th className="px-6 py-3 text-left">Error Code</th>
                  <th className="px-6 py-3 text-center">Retries</th>
                  <th className="px-6 py-3 text-left">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((tx) => (
                  <tr key={tx.id} className="hover:bg-blue-50 transition-colors">
                    <td className="px-6 py-3 text-gray-400 text-xs">{tx.id}</td>
                    <td className="px-6 py-3 font-mono text-xs text-blue-700">
                      {tx.razorpay_payment_id}
                    </td>
                    <td className="px-6 py-3 text-right font-semibold">{fmt(tx.amount)}</td>
                    <td className="px-6 py-3"><StatusBadge status={tx.status} /></td>
                    <td className="px-6 py-3"><CategoryBadge category={tx.root_cause_category} /></td>
                    <td className="px-6 py-3 font-mono text-xs text-gray-500">
                      {tx.failure_reason_code || "—"}
                    </td>
                    <td className="px-6 py-3 text-center">{tx.retry_count}</td>
                    <td className="px-6 py-3">
                      <button
                        onClick={() => openTx(tx)}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium hover:underline"
                      >
                        {tx.status === "failed" ? "▶ Recover" : "View →"}
                      </button>
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
