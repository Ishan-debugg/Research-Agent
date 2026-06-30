"use client";

import { useState } from "react";

/* ── Feature: Copy to clipboard on each card ── */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  function handleCopy(e) {
    e.stopPropagation();
    navigator.clipboard.writeText(text).then(function () {
      setCopied(true);
      setTimeout(function () { setCopied(false); }, 1800);
    });
  }

  return (
    <button
      onClick={handleCopy}
      title="Copy to clipboard"
      style={{
        background: "none",
        border: "none",
        cursor: "pointer",
        padding: "2px 4px",
        borderRadius: "4px",
        color: copied ? "var(--good)" : "var(--text-muted)",
        opacity: copied ? 1 : 0.5,
        transition: "opacity 0.15s, color 0.2s",
        display: "inline-flex",
        alignItems: "center",
      }}
    >
      {copied ? (
        /* checkmark */
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="2,7 5.5,11 12,3" />
        </svg>
      ) : (
        /* clipboard */
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="2" width="8" height="10" rx="1.5" />
          <path d="M4 4H3a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1v-1" />
        </svg>
      )}
    </button>
  );
}

export default function ProblemMethodGrid({ paper }) {
  const [hoveredLabel, setHoveredLabel] = useState(null);

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
        const hovered = hoveredLabel === label;
        return (
          <div
            key={label}
            onMouseEnter={function () { setHoveredLabel(label); }}
            onMouseLeave={function () { setHoveredLabel(null); }}
            className="border border-[var(--border)] rounded-md p-4 bg-[var(--surface-2)]"
            style={{ transition: "border-color 0.15s", borderColor: hovered ? "var(--accent)" : undefined }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)]">
                {label}
              </div>
              {/* Show copy button on hover */}
              {hovered && value && <CopyButton text={value} />}
            </div>
            <p className="text-sm text-[var(--text-muted)] leading-relaxed">{value}</p>
          </div>
        );
      })}
    </div>
  );
}
