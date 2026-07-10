// Map live stage name to a human-readable label for the status pill
const STAGE_LABELS = {
  retrieving:   "Querying arXiv…",
  retrieved:    "Papers retrieved",
  reranking:    "Ranking by relevance…",
  reranked:     "Reranking complete",
  downloading:  "Fetching paper text…",
  downloaded:   "Text ready",
  extracting:   "Gemini extracting…",
  extracted:    "Extraction done",
  synthesizing: "Building knowledge graph…",
  synthesized:  "Graph ready",
};

// Accent color stops per stage (0-indexed)
const STAGE_COLORS = [
  "#6ee7b7", // stage 1 — emerald
  "#93c5fd", // stage 2 — blue
  "#c4b5fd", // stage 3 — violet
  "#fbbf24", // stage 4 — amber
  "#f472b6", // stage 5 — pink
];

function slugify(text) {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

/**
 * PipelinePreviewWindow
 *
 * Props:
 *   query         — the search query string
 *   liveStage     — current SSE stage name (e.g. "extracting")
 *   liveProgress  — 1-5 integer
 *   liveMessage   — human-readable message from backend
 *   stageTimings  — array of {label, elapsed} for completed stages
 *   elapsedSeconds — running wall-clock stopwatch (from context)
 */
export default function PipelinePreviewWindow({
  query,
  liveStage,
  liveProgress,
  liveMessage,
  stageTimings = [],
  elapsedSeconds = 0,
}) {
  const breadcrumb = "copilot / research / " + (query ? slugify(query) : "insights");

  // Progress percentage from the live stage (1–5 → 20%–100%)
  const pct = liveProgress ? Math.round((liveProgress / 5) * 100) : 0;
  const stageIdx = liveProgress ? liveProgress - 1 : 0;
  const accentColor = STAGE_COLORS[Math.min(stageIdx, STAGE_COLORS.length - 1)];

  const stats = [
    { label: "CANDIDATES", value: "20",   caption: "papers from arXiv" },
    { label: "TOP-K",      value: "5",    caption: "after reranking" },
    {
      label: "ELAPSED",
      value: elapsedSeconds.toFixed(1) + "s",
      caption: STAGE_LABELS[liveStage] || "initialising…",
    },
  ];

  return (
    <div className="max-w-4xl mx-auto px-6 mb-8 w-full">
      <div
        className="rounded-xl border overflow-hidden"
        style={{
          borderColor: "var(--border)",
          background: "var(--surface)",
          boxShadow: `0 0 0 1px color-mix(in srgb, ${accentColor} 20%, transparent)`,
          transition: "box-shadow 0.5s ease",
        }}
      >
        {/* Window chrome */}
        <div className="flex items-center gap-2 px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
          <span className="w-2.5 h-2.5 rounded-full bg-[#e5605a]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#e5b95a]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#5ec46a]" />
          <span className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] ml-3 flex-1">
            {breadcrumb}
          </span>
          {/* Live badge */}
          {liveStage && (
            <span
              className="font-[var(--font-mono)] text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full flex items-center gap-1.5"
              style={{
                background: `color-mix(in srgb, ${accentColor} 15%, transparent)`,
                color: accentColor,
                border: `1px solid color-mix(in srgb, ${accentColor} 40%, transparent)`,
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full animate-pulse inline-block"
                style={{ background: accentColor }}
              />
              live
            </span>
          )}
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-px" style={{ background: "var(--border)" }}>
          {stats.map(function (s) {
            return (
              <div key={s.label} className="p-5" style={{ background: "var(--surface)" }}>
                <div className="font-[var(--font-mono)] text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-1.5">
                  {s.label}
                </div>
                <div
                  className="font-[var(--font-display)] text-2xl mb-1 tabular-nums transition-all duration-300"
                  style={s.label === "ELAPSED" ? { color: accentColor } : {}}
                >
                  {s.value}
                </div>
                <div className="text-xs text-[var(--text-muted)] transition-all duration-300">
                  {s.caption}
                </div>
              </div>
            );
          })}
        </div>

        {/* Per-stage timing pills — appear as each stage completes */}
        {stageTimings.length > 0 && (
          <div className="px-5 py-3 border-t flex flex-wrap gap-2" style={{ borderColor: "var(--border)" }}>
            {stageTimings.map(function (t, i) {
              const color = STAGE_COLORS[Math.min(i, STAGE_COLORS.length - 1)];
              return (
                <span
                  key={t.label}
                  className="font-[var(--font-mono)] text-[10px] px-2.5 py-1 rounded-full flex items-center gap-1.5"
                  style={{
                    background: `color-mix(in srgb, ${color} 12%, transparent)`,
                    color: color,
                    border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
                  }}
                >
                  <span>✓</span>
                  <span>{t.label}</span>
                  <span className="opacity-70">{t.elapsed}s</span>
                </span>
              );
            })}
          </div>
        )}

        {/* Progress bar */}
        <div className="px-5 py-4 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between mb-2">
            <span className="font-[var(--font-mono)] text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
              Pipeline progress
            </span>
            <span className="font-[var(--font-mono)] text-xs tabular-nums" style={{ color: accentColor }}>
              {pct}%
            </span>
          </div>

          {/* Segmented bar — 5 segments, each lights up per stage */}
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map(function (seg) {
              const filled = liveProgress >= seg;
              const segColor = STAGE_COLORS[Math.min(seg - 1, STAGE_COLORS.length - 1)];
              return (
                <div
                  key={seg}
                  className="h-1.5 flex-1 rounded-full transition-all duration-700"
                  style={{
                    background: filled
                      ? segColor
                      : "var(--border)",
                    opacity: filled ? 1 : 0.4,
                  }}
                />
              );
            })}
          </div>

          {/* Stage label */}
          {liveMessage && (
            <p className="font-[var(--font-mono)] text-[10px] mt-2 truncate" style={{ color: accentColor }}>
              {liveMessage}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
