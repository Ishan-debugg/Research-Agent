"use client";

import { useState, useMemo } from "react";

const METRIC_KEYS = [
  { key: "precision", label: "Precision" },
  { key: "recall", label: "Recall" },
  { key: "f1_score", label: "F1 Score" },
  { key: "accuracy", label: "Accuracy" },
];

function parseValue(raw) {
  if (!raw) return null;
  const match = String(raw).match(/(\d+(\.\d+)?)/);
  return match ? parseFloat(match[1]) : null;
}

function colorFor(raw) {
  const value = parseValue(raw);
  if (value === null) return "text-[var(--text-muted)] italic";
  if (value >= 90) return "text-[var(--good)]";
  if (value >= 70) return "text-[var(--accent)]";
  return "text-[var(--text)]";
}

export default function BenchmarkTable({ papers }) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("desc");

  const sorted = useMemo(
    function () {
      if (!sortKey) return papers;
      const withValues = papers.map(function (p) {
        return { paper: p, value: parseValue(p[sortKey]) };
      });
      withValues.sort(function (a, b) {
        const av = a.value === null ? -Infinity : a.value;
        const bv = b.value === null ? -Infinity : b.value;
        return sortDir === "desc" ? bv - av : av - bv;
      });
      return withValues.map(function (w) {
        return w.paper;
      });
    },
    [papers, sortKey, sortDir]
  );

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <>
      <div>
        <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
          <table className="w-full text-sm font-[var(--font-mono)]">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
                <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)]">
                  Paper
                </th>

                {METRIC_KEYS.map(function (m) {
                  const arrow =
                    sortKey === m.key ? (sortDir === "desc" ? " v" : " ^") : "";

                  return (
                    <th
                      key={m.key}
                      onClick={function () {
                        handleSort(m.key);
                      }}
                      className="text-left px-4 py-3 font-normal text-[var(--text-muted)] cursor-pointer hover:text-[var(--accent)] select-none"
                    >
                      {m.label + arrow}
                    </th>
                  );
                })}

                <th className="text-left px-4 py-3 font-normal text-[var(--text-muted)]">
                  Other
                </th>
              </tr>
            </thead>

            <tbody>
              {sorted.map(function (p) {
                return (
                  <tr
                    key={p.arxiv_id}
                    className="border-b border-[var(--border)] last:border-0"
                  >
                    <td className="px-4 py-3 font-[var(--font-body)] max-w-xs">
                      <a
                        href={p.pdf_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-[var(--accent)] hover:underline"
                      >
                        {p.title}
                      </a>
                    </td>

                    {METRIC_KEYS.map(function (m) {
                      return (
                        <td
                          key={m.key}
                          className={"px-4 py-3 " + colorFor(p[m.key])}
                        >
                          {p[m.key] || "Not reported"}
                        </td>
                      );
                    })}

                    <td className="px-4 py-3 text-[var(--text-muted)] max-w-xs">
                      {p.other_metrics || "Not reported"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <p className="text-xs text-[var(--text-muted)] mt-3 italic">
          Metrics extracted from the paper text where available. "Not reported"
          means the paper did not state that metric explicitly.
        </p>
      </div>
    </>
  );
}