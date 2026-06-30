import ProblemMethodGrid from "./ProblemMethodGrid";
import PaperNotes from "./PaperNotes";
import TechMatchBadges from "./TechMatchBadges";

export default function PaperDetail({ paper, techMatchItems, techStackSet, techMatchLoading }) {
  let authorLine = "";
  if (paper.authors && paper.authors.length > 0) {
    authorLine = paper.authors.slice(0, 3).join(", ");
    if (paper.authors.length > 3) authorLine += " et al.";
  }
  if (paper.year) {
    authorLine += authorLine ? " - " + paper.year : paper.year;
  }

  return (
    <div className="border border-[var(--border)] rounded-lg p-6 bg-[var(--surface)]">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div>
          <h3 className="font-[var(--font-display)] text-lg leading-snug">{paper.title}</h3>
          <p className="text-xs text-[var(--text-muted)] mt-1">{authorLine}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* PDF viewer */}
          <a
            href={paper.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs px-3 py-1.5 rounded-full border border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)] font-medium hover:opacity-80 transition-opacity"
          >
            View on arXiv
          </a>
          {/* Abstract page link */}
          <a
            href={"https://arxiv.org/abs/" + paper.arxiv_id}
            target="_blank"
            rel="noopener noreferrer"
            title="Open arXiv abstract page"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
          >
            Link
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 10L10 2" />
              <path d="M4 2h6v6" />
            </svg>
          </a>
        </div>
      </div>

      <ProblemMethodGrid paper={paper} />
      <PaperNotes paper={paper} />

      <div className="mt-6">
        <h4 className="text-sm font-medium mb-3">Tech Stack Match</h4>
        <TechMatchBadges items={techMatchItems} techStackSet={techStackSet} loading={techMatchLoading} />
      </div>
    </div>
  );
}
