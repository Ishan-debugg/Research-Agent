const ITEMS = [
  { n: "01", title: "Semantic synthesis", body: "Connect disparate concepts across journals using dense retrieval and cross-encoder reranking." },
  { n: "02", title: "Deep literature review", body: "Generate comprehensive meta-analyses across peer-reviewed sources in a single pass." },
  { n: "03", title: "Cited by default", body: "Every claim is anchored to a verifiable passage with deep links into the source PDF." },
  { n: "04", title: "Benchmarks extracted", body: "Precision, recall, F1, accuracy and domain metrics surfaced in one comparable table." },
  { n: "05", title: "Knowledge graph", body: "An interactive map of citations and conceptual neighbors. Click any node to read the summary." },
  { n: "06", title: "Direct to arXiv", body: "Every paper opens in its canonical source. No paywalls, no proxies, no surprises." },
];

export default function FeatureGrid() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-20">
      <div className="grid grid-cols-1 md:grid-cols-3 border-t border-l border-[var(--border)]">
        {ITEMS.map(function (item) {
          return (
            <div
              key={item.n}
              className="border-r border-b border-[var(--border)] p-8 hover:bg-[var(--surface)] transition-colors duration-200"
            >
              <div className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] mb-6">
                {item.n}
              </div>
              <h3 className="font-[var(--font-display)] text-xl mb-3">{item.title}</h3>
              <p className="text-sm text-[var(--text-muted)] leading-relaxed">{item.body}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}