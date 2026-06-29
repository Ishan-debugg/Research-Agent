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
        <a
          href={paper.pdf_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-xs px-3 py-1.5 rounded-full border border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)] font-medium hover:opacity-80 transition-opacity"
        >
          View on arXiv
        </a>
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
