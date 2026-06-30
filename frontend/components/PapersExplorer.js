"use client";

import { useState } from "react";
import PaperDetail from "./PaperDetail";

export default function PapersExplorer({ papers, techMatches, techStackSet, techMatchLoading }) {
  const [selectedId, setSelectedId] = useState(papers.length > 0 ? papers[0].arxiv_id : null);
  const selected = papers.find(function (p) {
    return p.arxiv_id === selectedId;
  });

  /* Score bar width: map relevance_score (0–100) to a percentage width */
  function barWidth(score) {
    return Math.max(10, Math.min(100, score || 0)) + "%";
  }

  return (
    <div style={{ display: "flex", gap: "0", alignItems: "flex-start" }}>
      {/* ── Left Sidebar ─────────────────────────────────────────── */}
      <aside
        style={{
          width: "260px",
          flexShrink: 0,
          position: "sticky",
          top: "80px",
          maxHeight: "calc(100vh - 120px)",
          overflowY: "auto",
          borderRight: "1px solid var(--border)",
          paddingRight: "0",
          marginRight: "0",
        }}
      >
        <p
          className="font-[var(--font-mono)]"
          style={{
            fontSize: "10px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            padding: "12px 16px 10px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          {papers.length} Papers · Ranked
        </p>

        <ul style={{ listStyle: "none", margin: 0, padding: "6px 0" }}>
          {papers.map(function (paper, i) {
            const active = paper.arxiv_id === selectedId;
            const score = paper.relevance_score || 0;

            return (
              <li key={paper.arxiv_id}>
                <button
                  onClick={function () { setSelectedId(paper.arxiv_id); }}
                  title={paper.title}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    background: active ? "var(--accent-soft, rgba(99,102,241,0.08))" : "transparent",
                    border: "none",
                    borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                    padding: "10px 14px 10px 14px",
                    cursor: "pointer",
                    transition: "background 0.15s, border-color 0.15s",
                  }}
                  onMouseEnter={function (e) {
                    if (!active) e.currentTarget.style.background = "var(--surface, rgba(255,255,255,0.04))";
                  }}
                  onMouseLeave={function (e) {
                    if (!active) e.currentTarget.style.background = "transparent";
                  }}
                >
                  {/* Rank + score row */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <span
                      className="font-[var(--font-mono)]"
                      style={{
                        fontSize: "10px",
                        color: active ? "var(--accent)" : "var(--text-muted)",
                        fontWeight: 600,
                      }}
                    >
                      #{i + 1}
                    </span>
                    <span
                      className="font-[var(--font-mono)]"
                      style={{
                        fontSize: "11px",
                        color: active ? "var(--accent)" : "var(--text-muted)",
                        fontWeight: 700,
                      }}
                    >
                      {score}%
                    </span>
                  </div>

                  {/* Title */}
                  <p
                    style={{
                      fontSize: "12px",
                      lineHeight: "1.45",
                      margin: "0 0 7px",
                      color: active ? "var(--text)" : "var(--text-muted)",
                      fontWeight: active ? 600 : 400,
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {paper.title}
                  </p>

                  {/* Relevance bar */}
                  <div
                    style={{
                      height: "2px",
                      borderRadius: "2px",
                      background: "var(--border)",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: barWidth(score),
                        background: active
                          ? "var(--accent)"
                          : "var(--text-muted)",
                        opacity: active ? 1 : 0.45,
                        borderRadius: "2px",
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      {/* ── Centre Content Panel ─────────────────────────────────── */}
      <div style={{ flex: 1, minWidth: 0, paddingLeft: "28px" }}>
        {selected && (
          <PaperDetail
            paper={selected}
            techMatchItems={techMatches ? techMatches[selected.arxiv_id] : null}
            techStackSet={techStackSet}
            techMatchLoading={techMatchLoading}
          />
        )}
      </div>
    </div>
  );
}
