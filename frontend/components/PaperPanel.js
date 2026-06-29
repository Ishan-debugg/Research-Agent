"use client";

export default function PaperPanel({ paper, onClose }) {
  if (!paper) return null;

  const fields = [
    ["Problem", paper.problem],
    ["Method", paper.method],
    ["Dataset", paper.dataset],
    ["Key Results", paper.results],
    ["Why It Matters", paper.real_world_impact],
  ];

  const allMetrics = [
    ["Precision", paper.precision],
    ["Recall", paper.recall],
    ["F1", paper.f1_score],
    ["Accuracy", paper.accuracy],
  ];
  const metrics = allMetrics.filter(function (pair) {
    return pair[1] && pair[1] !== "Not reported";
  });

  return (
    <div className="w-80 border-l border-[var(--border)] bg-[var(--bg)] p-6 overflow-y-auto">
      <div className="flex justify-between items-start gap-2 mb-2">
        <h2 className="text-sm font-medium leading-snug">{paper.title}</h2>
        <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text)] text-sm shrink-0">
          X
        </button>
      </div>
      <a
        href={paper.pdf_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block mt-2 text-xs px-3 py-1.5 rounded-full border border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)] font-medium hover:opacity-80 transition-opacity"
      >
        View on arXiv
      </a>

      {metrics.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-4">
          {metrics.map(function (pair) {
            const label = pair[0];
            const value = pair[1];
            return (
              <span key={label} className="text-xs font-[var(--font-mono)] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)]">
                {label + ": "}
                <span className="text-[var(--text)]">{value}</span>
              </span>
            );
          })}
        </div>
      )}

      <div className="mt-5 space-y-4">
        {fields.map(function (pair) {
          const label = pair[0];
          const value = pair[1];
          return (
            <div key={label}>
              <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)]">{label}</div>
              <div className="text-sm text-[var(--text-muted)] mt-1 leading-relaxed">{value}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}