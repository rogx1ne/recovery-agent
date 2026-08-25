// src/components/StatusBadge.jsx
export function StatusBadge({ status }) {
  const styles = {
    failed:          "bg-red-100 text-red-700 border border-red-300",
    retry_initiated: "bg-blue-100 text-blue-800 border border-blue-300",
    link_sent:       "bg-cyan-100 text-cyan-800 border border-cyan-300",
    recovered:       "bg-green-100 text-green-700 border border-green-300",
    escalated:       "bg-yellow-100 text-yellow-800 border border-yellow-300",
    pending:         "bg-gray-100 text-gray-600 border border-gray-300",
  };
  const icons = {
    failed: "✕", retry_initiated: "🔄", link_sent: "🔗", recovered: "✓", escalated: "⚠", pending: "…",
  };
  const cls = styles[status] || styles.pending;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      <span>{icons[status] || "?"}</span>
      <span className="capitalize">{status.replace(/_/g, " ")}</span>
    </span>
  );
}

export function StepBadge({ step }) {
  const colors = {
    detected:   "bg-blue-100 text-blue-700",
    classified: "bg-purple-100 text-purple-700",
    decided:    "bg-orange-100 text-orange-700",
    executed:   "bg-teal-100 text-teal-700",
    outcome:    "bg-green-100 text-green-700",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wide ${colors[step] || "bg-gray-100 text-gray-600"}`}>
      {step}
    </span>
  );
}

export function CategoryBadge({ category }) {
  if (!category) return <span className="text-gray-400 text-xs italic">uncategorised</span>;
  const colors = {
    card_declined:          "bg-red-50 text-red-600",
    insufficient_fund:      "bg-orange-50 text-orange-600",
    gateway_technical_error:"bg-blue-50 text-blue-600",
    authentication_failed:  "bg-purple-50 text-purple-600",
    subscription_failed:    "bg-yellow-50 text-yellow-700",
    unknown:                "bg-gray-50 text-gray-500",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[category] || "bg-gray-50 text-gray-500"}`}>
      {category.replace(/_/g, " ")}
    </span>
  );
}
