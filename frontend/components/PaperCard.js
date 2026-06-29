import PerformanceInsights from "./PerformanceInsights";
import TechMatchBadges from "./TechMatchBadges";

export default function PaperCard({ paper, techMatchItems, techStackSet, techMatchLoading }) {
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
        <div>
          <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-1">Problem</div>
          <p className="text-sm text-[var(--text-muted)] leading-relaxed">{paper.problem}</p>
        </div>
        <div>
          <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-1">Method</div>
          <p className="text-sm text-[var(--text-muted)] leading-relaxed">{paper.method}</p>
        </div>
      </div>

      <div className="mb-5 px-4 py-3 rounded-md bg-[var(--accent-soft)] border border-[var(--accent)]">
        <div className="text-xs font-[var(--font-mono)] uppercase tracking-wide text-[var(--accent)] mb-1">
          Why This Matters
        </div>
        <p className="text-sm text-[var(--text)]">{paper.real_world_impact}</p>
      </div>

      <div className="mb-5">
        <h4 className="text-sm font-medium mb-4">Key Performance & Insights</h4>
        <PerformanceInsights paper={paper} />
      </div>

      <div>
        <h4 className="text-sm font-medium mb-3">Tech Stack Match</h4>
        <TechMatchBadges items={techMatchItems} techStackSet={techStackSet} loading={techMatchLoading} />
      </div>
    </article>
  );
}