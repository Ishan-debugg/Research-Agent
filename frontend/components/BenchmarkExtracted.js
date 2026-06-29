const METRIC_FIELDS = [
  ["Precision", "precision"],
  ["Recall", "recall"],
  ["F1 Score", "f1_score"],
  ["Accuracy", "accuracy"],
  ["AUC", "auc"],
  ["BLEU", "bleu"],
  ["ROUGE", "rouge"],
];

function buildRows(papers) {
  const rows = [];
  papers.forEach(function (paper, paperIndex) {
    METRIC_FIELDS.forEach(function (pair) {
      const label = pair[0];
      const key = pair[1];
      const value = paper[key];
      if (value && value !== "Not reported") {
        rows.push({
          rank: paperIndex + 1,
          paperId: paper.arxiv_id,
          title: paper.title,
          pdf_url: paper.pdf_url,
          dataset: paper.dataset,
          metric: label,
          result: value,
          baseline: paper.baseline && paper.baseline !== "Not reported" ? paper.baseline : null,
        });
      }
    });
  });
  return rows;
}

export default function BenchmarkExtracted({ papers }) {
  const rows = buildRows(papers);

  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--text-muted)] italic">
        No benchmark metrics were explicitly reported across these papers.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full text-sm font-[var(--font-mono)]">
        <thead>
          <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
            <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)] w-10">#</th>
            <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)]">Paper</th>
            <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)]">Dataset</th>
            <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)]">Metric</th>
            <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)]">Result</th>
            <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)]">Baseline</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(function (row, i) {
            return (
              <tr key={row.paperId + row.metric + i} className="border-b border-[var(--border)] last:border-0">
                <td className="px-4 py-3 font-[var(--font-mono)] text-[var(--accent)] text-xs w-10">
                  #{row.rank}
                </td>
                <td className="px-4 py-3 font-[var(--font-body)] max-w-xs">
                  <a
                    href={row.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-[var(--accent)] hover:underline"
                  >
                    {row.title}
                  </a>
                </td>
                <td className="px-4 py-3 text-[var(--text-muted)]">{row.dataset}</td>
                <td className="px-4 py-3 text-[var(--text)]">{row.metric}</td>
                <td className="px-4 py-3 text-[var(--good)]">{row.result}</td>
                <td className="px-4 py-3 text-[var(--text-muted)]">{row.baseline || "-"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
