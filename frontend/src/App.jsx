// src/App.jsx — top-level router (no react-router needed, just state)
import { useState } from "react";
import { Navbar } from "./components/Navbar";
import { Dashboard } from "./pages/Dashboard";
import { Transactions } from "./pages/Transactions";
import { TransactionDetail } from "./pages/TransactionDetail";
import { AuditLog } from "./pages/AuditLog";

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [selectedTx, setSelectedTx] = useState(null);

  function navigate(p) {
    setPage(p);
    // Clear selected tx when navigating away from detail
    if (p !== "transaction") setSelectedTx(null);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar page={page} setPage={navigate} />

      <main className="pt-2">
        {page === "dashboard" && (
          <Dashboard setPage={navigate} setSelectedTx={setSelectedTx} />
        )}
        {page === "transactions" && (
          <Transactions setPage={navigate} setSelectedTx={setSelectedTx} />
        )}
        {page === "transaction" && selectedTx ? (
          <TransactionDetail tx={selectedTx} setPage={navigate} />
        ) : page === "transaction" && (
          <div className="text-center py-20 text-gray-400">
            No transaction selected. <button onClick={() => navigate("dashboard")} className="text-blue-600 underline">Go to Dashboard</button>
          </div>
        )}
        {page === "audit" && (
          <AuditLog setPage={navigate} setSelectedTx={setSelectedTx} />
        )}
      </main>

      {/* Footer */}
      <footer className="text-center text-xs text-gray-400 py-6 mt-12 border-t border-gray-200">
        Recovery Agent · Razorpay AI Buildathon 2026 · Track 03: Revenue Recovery
      </footer>
    </div>
  );
}
