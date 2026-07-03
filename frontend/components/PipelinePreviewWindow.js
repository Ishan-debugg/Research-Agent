function slugify(text) {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

// Map live stage name to a human-readable label for the status pill
const STAGE_LABELS = {
  retrieving:   "Querying arXiv…",
  retrieved:    "Papers retrieved",
  reranking:    "Ranking by relevance…",
  reranked:     "Reranking complete",
  downloading:  "Fetching PDFs…",
  downloaded:   "PDFs parsed",
  extracting:   "Gemini extracting…",
  extracted:    "Extraction done",
  synthesizing: "Building graph…",
  synthesized:  "Graph ready",
};

export default function PipelinePreviewWindow({ query, liveStage, liveProgress }) {
  const breadcrumb = "copilot / research / " + (query ? slugify(query) : "insights");

  // Progress percentage from the live stage (1–5 → 20%–100%)
  const pct = liveProgress ? Math.round((liveProgress / 5) * 100) : 0;

  const stats = [
    { label: "CANDIDATES", value: "20", caption: "papers from arXiv" },
    { label: "TOP-K",      value: "5",  caption: "after reranking" },
    { label: "STAGE",      value: liveProgress ? liveProgress + "/5" : "—", caption: STAGE_LABELS[liveStage] || "initialising…" },
  ];

  return (
    <div className="max-w-4xl mx-auto px-6 mb-12 w-full">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">

        {/* Window chrome */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)]">
          <span className="w-2.5 h-2.5 rounded-full bg-[#e5605a]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#e5b95a]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#5ec46a]" />
          <span className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] ml-3">
            {breadcrumb}
          </span>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-px bg-[var(--border)]">
          {stats.map(function (s) {
            return (
              <div key={s.label} className="bg-[var(--surface)] p-6">
                <div className="font-[var(--font-mono)] text-xs uppercase tracking-wide text-[var(--text-muted)] mb-2">
                  {s.label}
                </div>
                <div className="font-[var(--font-display)] text-3xl mb-1 transition-all duration-300">
                  {s.value}
                </div>
                <div className="text-xs text-[var(--text-muted)] transition-all duration-300">
                  {s.caption}
                </div>
              </div>
            );
          })}
        </div>

        {/* Progress bar — driven by real SSE liveProgress */}
        <div className="px-6 py-4 border-t border-[var(--border)]">
          <div className="flex items-center justify-between mb-2">
            <span className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] uppercase tracking-widest">
              Pipeline progress
            </span>
            <span className="font-[var(--font-mono)] text-xs text-[var(--accent)]">
              {pct}%
            </span>
          </div>
          <div className="w-full h-1 rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-all duration-700 ease-out"
              style={{ width: pct + "%" }}
            />
          </div>
        </div>

      </div>
    </div>
  );
}
