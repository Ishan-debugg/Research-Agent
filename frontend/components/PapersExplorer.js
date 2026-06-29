"use client";

import { useState } from "react";
import PaperDetail from "./PaperDetail";

export default function PapersExplorer({ papers, techMatches, techStackSet, techMatchLoading }) {
  const [selectedId, setSelectedId] = useState(papers.length > 0 ? papers[0].arxiv_id : null);
  const selected = papers.find(function (p) {
    return p.arxiv_id === selectedId;
  });

  return (
    <div>
      <p className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] mb-3">
        {papers.length + " papers - ranked by relevance"}
      </p>

      <div className="space-y-2 mb-6">
        {papers.map(function (paper, i) {
          const active = paper.arxiv_id === selectedId;
          return (
            <button
              key={paper.arxiv_id}
              onClick={function () {
                setSelectedId(paper.arxiv_id);
              }}
              className={
                "w-full text-left px-4 py-3 rounded-md border flex items-center justify-between gap-4 transition-colors " +
                (active
                  ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                  : "border-[var(--border)] hover:border-[var(--text-muted)]")
              }
            >
              <span className="flex items-center gap-3 min-w-0">
                <span className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] shrink-0">
                  {"#" + (i + 1)}
                </span>
                <span className="text-sm truncate">{paper.title}</span>
              </span>
              <span className="font-[var(--font-mono)] text-xs text-[var(--accent)] shrink-0">
                {(paper.relevance_score || 0) + "%"}
              </span>
            </button>
          );
        })}
      </div>

      {selected && (
        <PaperDetail
          paper={selected}
          techMatchItems={techMatches ? techMatches[selected.arxiv_id] : null}
          techStackSet={techStackSet}
          techMatchLoading={techMatchLoading}
        />
      )}
    </div>
  );
}
