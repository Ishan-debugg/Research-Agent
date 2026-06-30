"use client";

import { useState } from "react";

const LEVEL_STYLES = {
  high: {
    color: "var(--good)",
    border: "var(--good)",
    bgHover: "rgba(95, 174, 122, 0.18)",
  },
  moderate: {
    color: "var(--warn)",
    border: "var(--warn)",
    bgHover: "rgba(214, 181, 61, 0.18)",
  },
  low: {
    color: "var(--bad)",
    border: "var(--bad)",
    bgHover: "rgba(199, 84, 80, 0.18)",
  },
};

const DEFAULT_STYLE = {
  color: "var(--text-muted)",
  border: "var(--border)",
  bgHover: "rgba(142, 140, 151, 0.14)",
};

function TechBadge({ item }) {
  const [hovered, setHovered] = useState(false);
  const s = LEVEL_STYLES[item.level] || DEFAULT_STYLE;

  return (
    <span
      title={item.explanation}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        fontSize: "12px",
        padding: "4px 10px",
        borderRadius: "6px",
        border: `1px solid ${s.border}`,
        color: s.color,
        background: hovered ? s.bgHover : "transparent",
        transition: "background 0.18s ease",
        cursor: "default",
      }}
    >
      {item.tech}: {item.level}
    </span>
  );
}

export default function TechMatchBadges({ items, techStackSet, loading }) {
  if (!techStackSet) {
    return (
      <p className="text-xs text-[var(--text-muted)] italic">
        Set your tech stack in Settings to see a match score here.
      </p>
    );
  }
  if (loading) {
    return <p className="text-xs text-[var(--text-muted)]">Checking match...</p>;
  }
  if (!items || items.length === 0) {
    return <p className="text-xs text-[var(--text-muted)]">No match data.</p>;
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
      {items.map(function (item) {
        return <TechBadge key={item.tech} item={item} />;
      })}
    </div>
  );
}