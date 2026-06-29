const LEVEL_CLASS = {
  high: "text-[var(--good)] border-[var(--good)]",
  moderate: "text-[var(--warn)] border-[var(--warn)]",
  low: "text-[var(--bad)] border-[var(--bad)]",
};

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
    <div className="flex flex-wrap gap-2">
      {items.map(function (item) {
        const cls = LEVEL_CLASS[item.level] || "text-[var(--text-muted)] border-[var(--border)]";
        return (
          <span key={item.tech} title={item.explanation} className={"text-xs px-2 py-1 rounded border " + cls}>
            {item.tech + ": " + item.level}
          </span>
        );
      })}
    </div>
  );
}