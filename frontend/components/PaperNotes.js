export default function PaperNotes({ paper }) {
  const rows = [
    ["Contribution / Novelty", paper.contribution],
    ["Limitations", paper.limitations],
    ["Prerequisites", paper.prerequisites],
  ];

  return (
    <div className="space-y-4 mt-5">
      {rows.map(function (pair) {
        const label = pair[0];
        const value = pair[1];
        return (
          <div key={label}>
            <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--text)] mb-1">
              {label}
            </div>
            <p className="text-sm text-[var(--text-muted)] leading-relaxed">{value}</p>
          </div>
        );
      })}
    </div>
  );
}
