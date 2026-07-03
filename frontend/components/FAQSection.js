const FAQS = [
  {
    q: "Where do the papers come from?",
    a: "Every paper is pulled live from arXiv at search time. Nothing is pre-indexed or cached from a static dataset.",
  },
  {
    q: "How are benchmark metrics extracted?",
    a: 'Where a paper reports Precision, Recall, F1, Accuracy, or similar metrics in its text, they are pulled out directly. If a paper does not report a metric, it is marked "Not reported" rather than estimated. Any custom or niche metrics are captured under "Other Metrics".',
  },
  {
    q: "Can I trust the synthesized summary?",
    a: "Treat it as a fast first read, not a substitute for the paper. Every result links back to its arXiv source so you can verify anything that matters.",
  },
  {
    q: "Why only 5 papers per search?",
    a: "Depth over breadth. Reading 5 papers properly, full text and not just abstracts, produces a more reliable landscape than skimming 20. The pipeline analyzes up to 20 candidates and reranks them to find the best 5 before extracting text.",
  },
  {
    q: "Is there a limit on searches?",
    a: "To ensure fair usage of the AI models, searches are limited to 10 requests per minute per IP address. If you exceed this, you will see a 'Slow down!' message.",
  }
];

export default function FAQSection() {
  return (
    <section className="max-w-3xl mx-auto px-6 py-20">
      <h2 className="font-[var(--font-display)] text-2xl mb-8">
        FAQs
      </h2>
      <div className="divide-y divide-[var(--border)]">
        {FAQS.map(function (item) {
          return (
            <details key={item.q} className="group py-5">
              <summary className="flex justify-between items-center cursor-pointer list-none outline-none">
                <span className="font-medium group-focus-visible:text-[var(--accent)] transition-colors">{item.q}</span>
                <span className="text-[var(--text-muted)] group-open:rotate-45 transition-transform">
                  +
                </span>
              </summary>
              <p className="text-sm text-[var(--text-muted)] mt-3 leading-relaxed">
                {item.a}
              </p>
            </details>
          );
        })}
      </div>
    </section>
  );
}