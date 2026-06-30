"use client";

import { useState, useEffect, useRef } from "react";
import PaperDetail from "./PaperDetail";

export default function PapersExplorer({ papers, techMatches, techStackSet, techMatchLoading }) {
  const [selectedId, setSelectedId] = useState(papers.length > 0 ? papers[0].arxiv_id : null);
  /* ── Feature: Comparison mode ── */
  const [compareId, setCompareId] = useState(null);
  /* ── Improvement: Abstract preview on hover ── */
  const [hoveredId, setHoveredId] = useState(null);

  const selected = papers.find((p) => p.arxiv_id === selectedId);
  const compareSelected = papers.find((p) => p.arxiv_id === compareId);

  const listRef = useRef(null);
  const selectedIndex = papers.findIndex((p) => p.arxiv_id === selectedId);

  /* ── Improvement: Keyboard navigation ── */
  useEffect(function () {
    function handleKey(e) {
      if (!listRef.current) return;
      // Only handle arrow keys when sidebar has focus or nothing is focused
      const active = document.activeElement;
      const inInput = active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA");
      if (inInput) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        const nextIdx = Math.min(selectedIndex + 1, papers.length - 1);
        setSelectedId(papers[nextIdx].arxiv_id);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prevIdx = Math.max(selectedIndex - 1, 0);
        setSelectedId(papers[prevIdx].arxiv_id);
      } else if (e.key === "Escape") {
        setCompareId(null);
      }
    }
    window.addEventListener("keydown", handleKey);
    return function () { window.removeEventListener("keydown", handleKey); };
  }, [selectedIndex, papers]);

  function barWidth(score) {
    return Math.max(10, Math.min(100, score || 0)) + "%";
  }

  function toggleCompare(paperId, e) {
    e.stopPropagation();
    setCompareId(function (prev) { return prev === paperId ? null : paperId; });
  }

  const isComparing = compareId && compareId !== selectedId;

  return (
    /* ── Improvement: Responsive — stacks on mobile, side-by-side on md+ ── */
    <div className="flex flex-col md:flex-row" style={{ alignItems: "flex-start" }}>

      {/* ── Left Sidebar ── */}
      <aside
        ref={listRef}
        className="md:sticky"
        style={{
          width: "100%",
          maxWidth: "260px",
          flexShrink: 0,
          top: "80px",
          maxHeight: "calc(100vh - 120px)",
          overflowY: "auto",
          borderRight: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
          marginBottom: "0",
        }}
      >
        <div
          className="font-[var(--font-mono)]"
          style={{
            fontSize: "10px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            padding: "10px 14px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{papers.length} Papers · Ranked</span>
          <span style={{ opacity: 0.5 }}>↑↓ navigate</span>
        </div>

        <ul style={{ listStyle: "none", margin: 0, padding: "6px 0" }}>
          {papers.map(function (paper, i) {
            const active = paper.arxiv_id === selectedId;
            const comparing = paper.arxiv_id === compareId;
            const hovered = paper.arxiv_id === hoveredId;
            const score = paper.relevance_score || 0;

            return (
              <li key={paper.arxiv_id} style={{ position: "relative" }}>
                <button
                  onClick={function () { setSelectedId(paper.arxiv_id); }}
                  onMouseEnter={function (e) {
                    setHoveredId(paper.arxiv_id);
                    if (!active) e.currentTarget.style.background = "var(--surface)";
                  }}
                  onMouseLeave={function (e) {
                    setHoveredId(null);
                    if (!active) e.currentTarget.style.background = "transparent";
                  }}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    background: active ? "var(--accent-soft)" : comparing ? "rgba(95,174,122,0.07)" : "transparent",
                    border: "none",
                    borderLeft: active
                      ? "2px solid var(--accent)"
                      : comparing
                      ? "2px solid var(--good)"
                      : "2px solid transparent",
                    padding: "10px 12px 10px 12px",
                    cursor: "pointer",
                    transition: "background 0.15s, border-color 0.15s",
                  }}
                >
                  {/* Rank + score */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <span className="font-[var(--font-mono)]" style={{ fontSize: "10px", color: active ? "var(--accent)" : "var(--text-muted)", fontWeight: 600 }}>
                      #{i + 1}
                      {comparing && <span style={{ color: "var(--good)", marginLeft: 6 }}>⊕ compare</span>}
                    </span>
                    <span className="font-[var(--font-mono)]" style={{ fontSize: "11px", color: active ? "var(--accent)" : "var(--text-muted)", fontWeight: 700 }}>
                      {score}%
                    </span>
                  </div>

                  {/* Title */}
                  <p style={{
                    fontSize: "12px",
                    lineHeight: "1.45",
                    margin: "0 0 7px",
                    color: active ? "var(--text)" : "var(--text-muted)",
                    fontWeight: active ? 600 : 400,
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}>
                    {paper.title}
                  </p>

                  {/* ── Feature: Abstract preview on hover ── */}
                  {hovered && !active && paper.abstract && (
                    <p style={{
                      fontSize: "11px",
                      lineHeight: "1.4",
                      color: "var(--text-muted)",
                      margin: "0 0 7px",
                      display: "-webkit-box",
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      opacity: 0.8,
                      fontStyle: "italic",
                    }}>
                      {paper.abstract}
                    </p>
                  )}

                  {/* Relevance bar */}
                  <div style={{ height: "2px", borderRadius: "2px", background: "var(--border)", overflow: "hidden" }}>
                    <div style={{
                      height: "100%",
                      width: barWidth(score),
                      background: active ? "var(--accent)" : comparing ? "var(--good)" : "var(--text-muted)",
                      opacity: active || comparing ? 1 : 0.4,
                      borderRadius: "2px",
                      transition: "width 0.3s ease",
                    }} />
                  </div>
                </button>

                {/* ── Feature: Comparison pin button (visible on hover) ── */}
                {hovered && !active && (
                  <button
                    onClick={function (e) { toggleCompare(paper.arxiv_id, e); }}
                    title={comparing ? "Remove from comparison" : "Compare with selected paper"}
                    style={{
                      position: "absolute",
                      bottom: "12px",
                      right: "10px",
                      fontSize: "10px",
                      padding: "2px 7px",
                      borderRadius: "4px",
                      border: `1px solid ${comparing ? "var(--good)" : "var(--border)"}`,
                      color: comparing ? "var(--good)" : "var(--text-muted)",
                      background: "var(--surface)",
                      cursor: "pointer",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {comparing ? "✕ unpin" : "⊕ compare"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>

        {isComparing && (
          <div style={{
            padding: "8px 12px",
            borderTop: "1px solid var(--border)",
            fontSize: "10px",
            color: "var(--good)",
          }} className="font-[var(--font-mono)]">
            Comparing 2 papers · Esc to clear
          </div>
        )}
      </aside>

      {/* ── Centre Content Panel ── */}
      <div
        className="flex-1 min-w-0"
        style={{ paddingLeft: "28px", paddingTop: "0" }}
      >
        {/* ── Feature: Comparison mode — side-by-side ── */}
        {isComparing ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            {selected && (
              <div>
                <div className="font-[var(--font-mono)]" style={{ fontSize: "10px", color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "8px" }}>
                  ● Selected
                </div>
                <PaperDetail
                  paper={selected}
                  techMatchItems={techMatches ? techMatches[selected.arxiv_id] : null}
                  techStackSet={techStackSet}
                  techMatchLoading={techMatchLoading}
                />
              </div>
            )}
            {compareSelected && (
              <div>
                <div className="font-[var(--font-mono)]" style={{ fontSize: "10px", color: "var(--good)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "8px" }}>
                  ⊕ Comparing
                </div>
                <PaperDetail
                  paper={compareSelected}
                  techMatchItems={techMatches ? techMatches[compareSelected.arxiv_id] : null}
                  techStackSet={techStackSet}
                  techMatchLoading={techMatchLoading}
                />
              </div>
            )}
          </div>
        ) : (
          selected && (
            <PaperDetail
              paper={selected}
              techMatchItems={techMatches ? techMatches[selected.arxiv_id] : null}
              techStackSet={techStackSet}
              techMatchLoading={techMatchLoading}
            />
          )
        )}
      </div>
    </div>
  );
}
