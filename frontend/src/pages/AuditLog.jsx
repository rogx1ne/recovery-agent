// src/pages/AuditLog.jsx — Screen: global audit trail with reasoning visible
import { useEffect, useState } from "react";
import { api } from "../api";
import { StepBadge } from "../components/StatusBadge";

export function AuditLog({ setPage, setSelectedTx }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    api.listAuditLogs(100).then((r) => {
      setLogs(r.items || []);
      setLoading(false);
    });
  }, []);

  function toggle(id) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Audit Log</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Every decision the AI agent made, with full reasoning. Click a row to expand.
        </p>
      </div>

      {loading ? (
        <div className="p-8 text-center text-gray-400">Loading audit logs…</div>
      ) : logs.length === 0 ? (
        <div className="p-12 text-center text-gray-400">
          No audit logs yet. Run recovery on a transaction first.
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-6 py-3 bg-gray-50 border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wider grid grid-cols-12 gap-2 font-semibold">
            <span className="col-span-1">ID</span>
            <span className="col-span-2">Tx</span>
            <span className="col-span-2">Step</span>
            <span className="col-span-5">Detail</span>
            <span className="col-span-2">Time</span>
          </div>
          <div className="divide-y divide-gray-100">
            {logs.map((log) => (
              <div key={log.id}>
                <button
                  onClick={() => toggle(log.id)}
                  className="w-full px-6 py-3 grid grid-cols-12 gap-2 items-start text-left hover:bg-gray-50 transition-colors"
                >
                  <span className="col-span-1 text-gray-400 text-xs">{log.id}</span>
                  <span className="col-span-2 text-xs font-mono text-blue-600">
                    #{log.transaction_id}
                  </span>
                  <span className="col-span-2">
                    <StepBadge step={log.step} />
                  </span>
                  <span className="col-span-5 text-sm text-gray-700 text-left truncate">
                    {log.detail}
                  </span>
                  <span className="col-span-2 text-xs text-gray-400">
                    {new Date(log.timestamp).toLocaleTimeString("en-IN")}
                    <span className="ml-1 text-gray-300">{expanded[log.id] ? "▲" : "▼"}</span>
                  </span>
                </button>

                {/* Expanded reasoning */}
                {expanded[log.id] && (
                  <div className="px-6 pb-4 bg-purple-50 border-t border-purple-100">
                    <p className="text-xs font-semibold text-purple-500 uppercase mt-3 mb-1">
                      AI Reasoning
                    </p>
                    <p className="text-sm text-gray-700 leading-relaxed">{log.reasoning}</p>
                    <div className="flex gap-3 mt-3">
                      <button
                        onClick={() => {
                          api.getTransaction(log.transaction_id).then((tx) => {
                            setSelectedTx(tx);
                            setPage("transaction");
                          });
                        }}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        View transaction →
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
