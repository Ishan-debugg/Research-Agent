"use client";

import { useState } from "react";

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
          metricKey: key,
          result: value,
          baseline: paper.baseline && paper.baseline !== "Not reported" ? paper.baseline : null,
        });
      }
    });
  });
  return rows;
}

const SORT_COLS = ["rank", "title", "dataset", "metric", "result", "baseline"];

export default function BenchmarkExtracted({ papers }) {
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState(1); // 1=asc, -1=desc

  const allRows = buildRows(papers);

  /* ── Improvement: Sortable columns ── */
  function handleSort(key) {
    if (sortKey === key) {
      setSortDir(function (d) { return d * -1; });
    } else {
      setSortKey(key);
      setSortDir(1);
    }
  }

  const rows = [...allRows].sort(function (a, b) {
    const av = a[sortKey] ?? "";
    const bv = b[sortKey] ?? "";
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
    return String(av).localeCompare(String(bv)) * sortDir;
  });

  /* ── Improvement: Better empty state ── */
  if (allRows.length === 0) {
    return (
      <div
        style={{
          border: "1px dashed var(--border)",
          borderRadius: "10px",
          padding: "32px 24px",
          textAlign: "center",
          background: "var(--surface)",
        }}
      >
        <p className="font-[var(--font-display)] text-base mb-1">No numeric benchmarks reported</p>
        <p className="text-xs text-[var(--text-muted)] leading-relaxed max-w-sm mx-auto">
          These papers did not explicitly state numeric values for Precision, Recall, F1, Accuracy,
          AUC, BLEU, or ROUGE. Qualitative findings may still appear in the paper details below.
        </p>
      </div>
    );
  }

  function SortIcon({ col }) {
    if (sortKey !== col) return <span style={{ opacity: 0.25, marginLeft: 4 }}>↕</span>;
    return <span style={{ marginLeft: 4, color: "var(--accent)" }}>{sortDir === 1 ? "↑" : "↓"}</span>;
  }

  const colLabel = { rank: "#", title: "Paper", dataset: "Dataset", metric: "Metric", result: "Result", baseline: "Baseline" };

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full text-sm font-[var(--font-mono)]">
        <thead>
          <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
            {SORT_COLS.map(function (col) {
              return (
                <th
                  key={col}
                  onClick={function () { handleSort(col); }}
                  className="text-left px-4 py-3 font-normal text-[var(--text-muted)] select-none"
                  style={{ cursor: "pointer", whiteSpace: "nowrap" }}
                  title={"Sort by " + colLabel[col]}
                >
                  {colLabel[col]}
                  <SortIcon col={col} />
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map(function (row, i) {
            return (
              <tr key={row.paperId + row.metric + i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-2)] transition-colors">
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
                <td className="px-4 py-3 text-[var(--text-muted)]">{row.dataset || "—"}</td>
                <td className="px-4 py-3 text-[var(--text)]">{row.metric}</td>
                <td className="px-4 py-3 text-[var(--good)] font-medium">{row.result}</td>
                <td className="px-4 py-3 text-[var(--text-muted)]">{row.baseline || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div
        style={{
          padding: "8px 16px",
          borderTop: "1px solid var(--border)",
          fontSize: "10px",
          color: "var(--text-muted)",
        }}
        className="font-[var(--font-mono)]"
      >
        {rows.length} metric{rows.length !== 1 ? "s" : ""} · click any column header to sort
      </div>
    </div>
  );
}
