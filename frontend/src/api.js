// src/api.js — all backend calls in one place
// Vite proxies /api → localhost:8000, so no CORS issues in dev.
// In production, set VITE_API_URL to the full backend URL.
const BASE_URL = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/v1`
  : "/api/v1";

async function request(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE_URL}${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export const api = {
  // Transactions
  listTransactions: (limit = 50, offset = 0, batchId = null) =>
    request(
      "GET",
      `/transactions/?limit=${limit}&offset=${offset}${batchId ? `&batch_id=${encodeURIComponent(batchId)}` : ""}`
    ),
  getTransaction: (id) => request("GET", `/transactions/${id}`),

  // Recovery
  triggerRecovery: (id) => request("POST", `/recovery/${id}`, {}),
  getRecoveryStatus: (id) => request("GET", `/recovery/${id}/status`),

  // Audit
  getAuditTrail: (txId) => request("GET", `/audit/transaction/${txId}`),
  listAuditLogs: (limit = 20) => request("GET", `/audit/?limit=${limit}`),

  // Stats (renamed from /stats to avoid ad blocker blocks)
  listBatches: () => request("GET", `/stats/batches`),
  getSummary: (batchId = null) =>
    request("GET", `/stats/summary${batchId ? `?batch_id=${encodeURIComponent(batchId)}` : ""}`),
  getByCategory: (batchId = null) =>
    request("GET", `/stats/by-category${batchId ? `?batch_id=${encodeURIComponent(batchId)}` : ""}`),

  // Demo Runner
  runDemoBatch: () => request("POST", `/demo/run-batch`, {}),
  getDemoStatus: (batchId) => request("GET", `/demo/status/${encodeURIComponent(batchId)}`),
};

