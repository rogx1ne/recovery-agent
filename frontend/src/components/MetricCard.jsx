// src/components/MetricCard.jsx
export function MetricCard({ label, value, sub, accent }) {
  const accents = {
    green:  "border-l-green-500 bg-green-50",
    red:    "border-l-red-400 bg-red-50",
    blue:   "border-l-blue-500 bg-blue-50",
    yellow: "border-l-yellow-400 bg-yellow-50",
    gray:   "border-l-gray-400 bg-gray-50",
  };
  return (
    <div className={`rounded-xl border-l-4 p-5 shadow-sm ${accents[accent] || accents.gray}`}>
      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-1">{label}</p>
      <p className="text-3xl font-bold text-gray-800">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}
