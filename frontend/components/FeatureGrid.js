const FEATURES = [
  {
    numeral: "I",
    title: "Retrieve",
    body: "Pulls 20 candidate papers straight from arXiv for any topic, in plain English.",
  },
  {
    numeral: "II",
    title: "Rerank",
    body: "A cross-encoder reads query and abstract together to surface the 5 most relevant papers.",
  },
  {
    numeral: "III",
    title: "Extract",
    body: "Full PDF text is parsed and distilled into problem, method, dataset, results, and benchmarks.",
  },
  {
    numeral: "IV",
    title: "Synthesize",
    body: "A knowledge graph maps how the papers relate, and where the open problems still are.",
  },
];

export default function FeatureGrid() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-20">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-px bg-[var(--border)] rounded-xl overflow-hidden">
        {FEATURES.map(function (f) {
          return (
            <div key={f.numeral} className="bg-[var(--surface)] p-6">
              <div className="font-[var(--font-display)] text-2xl text-[var(--accent)] mb-3">
                {f.numeral}
              </div>
              <h3 className="font-medium mb-2">{f.title}</h3>
              <p className="text-sm text-[var(--text-muted)] leading-relaxed">
                {f.body}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}