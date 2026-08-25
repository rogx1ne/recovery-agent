// src/components/Navbar.jsx
export function Navbar({ page, setPage }) {
  const links = [
    { id: "dashboard", label: "Dashboard" },
    { id: "transactions", label: "Transactions" },
    { id: "audit", label: "Audit Log" },
  ];
  return (
    <nav className="bg-[#1a1a2e] text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-6 flex items-center justify-between h-14">
        {/* Logo */}
        <button
          onClick={() => setPage("dashboard")}
          className="flex items-center gap-2 font-bold text-lg tracking-tight"
        >
          <span className="text-blue-400">⚡</span>
          <span>Recovery Agent</span>
          <span className="ml-2 text-xs bg-blue-600 px-2 py-0.5 rounded-full font-normal">
            Razorpay Buildathon
          </span>
        </button>

        {/* Nav links */}
        <div className="flex gap-1">
          {links.map((l) => (
            <button
              key={l.id}
              onClick={() => setPage(l.id)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                page === l.id
                  ? "bg-blue-600 text-white"
                  : "text-gray-300 hover:text-white hover:bg-white/10"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>
    </nav>
  );
}
