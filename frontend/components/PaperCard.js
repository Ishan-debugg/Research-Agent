export default function PaperCard({ paper }) {
  const fields = [
    ["Problem", paper.problem],
    ["Method", paper.method],
    ["Key Results", paper.results],
    ["Why It Matters", paper.contribution],
  ];

  let authorLine = "";
  if (paper.authors && paper.authors.length > 0) {
    authorLine = paper.authors.slice(0, 3).join(", ");
    if (paper.authors.length > 3) authorLine += " et al.";
  }
  if (paper.year) {
    authorLine += authorLine ? " - " + paper.year : paper.year;
  }

  return (
    <article className="border border-[var(--border)] rounded-lg p-6 bg-[var(--surface)]">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h3 className="font-medium text-base leading-snug">{paper.title}</h3>
          <p className="text-xs text-[var(--text-muted)] mt-1">{authorLine}</p>
        </div>
        
         <a href={paper.pdf_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-xs px-3 py-1.5 rounded-full border border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
        >
          View on arXiv
        </a>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {fields.map(function (pair) {
          const label = pair[0];
          const value = pair[1];
          return (
            <div key={label}>
              <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-1">
                {label}
              </div>
              <p className="text-sm text-[var(--text-muted)] leading-relaxed">
                {value}
              </p>
            </div>
          );
        })}
      </div>
    </article>
  );
}
    