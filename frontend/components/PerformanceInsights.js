const METRIC_ROWS = [
  ["Accuracy", "accuracy"],
  ["F1 Score", "f1_score"],
  ["Precision", "precision"],
  ["Recall", "recall"],
  ["BLEU", "bleu"],
  ["ROUGE", "rouge"],
];

export default function PerformanceInsights({ paper }) {
  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-2">
          {"\uD83D\uDCCA Performance"}
        </div>
        <div className="flex flex-wrap gap-2">
          {METRIC_ROWS.map(function (pair) {
            const label = pair[0];
            const key = pair[1];
            const value = paper[key] || "Not reported";
            const reported = value !== "Not reported";
            return (
              <span
                key={key}
                className={
                  "text-xs px-2 py-1 rounded border border-[var(--border)] " +
                  (reported ? "text-[var(--text)]" : "text-[var(--text-muted)] italic")
                }
              >
                {label + ": " + value}
              </span>
            );
          })}
        </div>
        {paper.results && (
          <p className="text-sm text-[var(--text-muted)] mt-2 leading-relaxed">{paper.results}</p>
        )}
      </div>

      <div>
        <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-2">
          {"\uD83D\uDCDA Dataset & Evaluation Setup"}
        </div>
        <p className="text-sm text-[var(--text-muted)] leading-relaxed">
          {(paper.dataset || "Not specified") + " - " + (paper.eval_method || "Not specified")}
        </p>
      </div>

      <div>
        <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-2">
          {"\uD83C\uDFAF Contribution / Novelty"}
        </div>
        <p className="text-sm text-[var(--text-muted)] leading-relaxed">{paper.contribution}</p>
      </div>

      <div>
        <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--bad)] mb-2">
          {"\u26A0\uFE0F Limitations"}
        </div>
        <p className="text-sm text-[var(--text-muted)] leading-relaxed">{paper.limitations}</p>
      </div>

      <div>
        <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--text-muted)] mb-2">
          {"\uD83D\uDCCC Prerequisites"}
        </div>
        <p className="text-sm text-[var(--text-muted)] leading-relaxed">{paper.prerequisites}</p>
      </div>
    </div>
  );
}
