function slugify(text) {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export default function PipelinePreviewWindow({ query, edgeCount }) {
  const stats = [
    { label: "RETRIEVED", value: "20", caption: "papers - arXiv API" },
    { label: "RERANKED", value: "5", caption: "top - cross-encoder" },
    { label: "EXTRACT", value: "5", caption: "PDFs - full text parsed" },
    {
      label: "SYNTHESIZE",
      value: edgeCount === null || edgeCount === undefined ? "-" : String(edgeCount),
      caption: "relationships found",
    },
  ];

  const breadcrumb = "copilot / research / " + (query ? slugify(query) : "insights");

  return (
    <div className="max-w-4xl mx-auto px-6 mb-12">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)]">
          <span className="w-2.5 h-2.5 rounded-full bg-[#e5605a]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#e5b95a]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#5ec46a]" />
          <span className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] ml-3">
            {breadcrumb}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-[var(--border)]">
          {stats.map(function (s) {
            return (
              <div key={s.label} className="bg-[var(--surface)] p-6">
                <div className="font-[var(--font-mono)] text-xs uppercase tracking-wide text-[var(--text-muted)] mb-2">
                  {s.label}
                </div>
                <div className="font-[var(--font-display)] text-3xl mb-1">{s.value}</div>
                <div className="text-xs text-[var(--text-muted)]">{s.caption}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
