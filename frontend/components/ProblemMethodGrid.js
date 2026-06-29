export default function ProblemMethodGrid({ paper }) {
  const items = [
    ["Problem", paper.problem],
    ["Method", paper.method],
    ["Why It Matters", paper.real_world_impact],
    ["Audience", paper.audience],
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map(function (pair) {
        const label = pair[0];
        const value = pair[1];
        return (
          <div key={label} className="border border-[var(--border)] rounded-md p-4 bg-[var(--surface-2)]">
            <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-2">
              {label}
            </div>
            <p className="text-sm text-[var(--text-muted)] leading-relaxed">{value}</p>
          </div>
        );
      })}
    </div>
  );
}
