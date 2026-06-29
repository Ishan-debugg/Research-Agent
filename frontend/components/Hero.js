import Image from "next/image";
import Link from "next/link";

const BADGES = ["arXiv", "Gemini 3.1 Flash-Lite", "Cross-Encoder Reranking", "PyMuPDF"];

export default function Hero() {
  return (
    <section className="max-w-6xl mx-auto px-6 pt-24 pb-16">
      <div className="flex flex-col md:flex-row items-center gap-10">
        {/* Left: text content */}
        <div className="flex-1 min-w-0">
          <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-6">
            [ arXiv-native research engine ]
          </p>
          <h1 className="font-[var(--font-display)] text-4xl md:text-6xl leading-[1.1] max-w-3xl">
            Accelerate Research Intelligence.
          </h1>
          <p className="text-[var(--text-muted)] text-lg mt-6 max-w-xl leading-relaxed">
            Research Copilot retrieves, reranks, and synthesizes machine learning
            papers from arXiv into a structured research landscape — problems,
            methods, benchmarks, and open questions, with every claim linked back
            to its source.
          </p>
          <Link
            href="/search"
            className="inline-block mt-10 px-7 py-3 rounded-md bg-[var(--accent)] text-[var(--bg)] font-medium hover:opacity-90 transition-opacity"
          >
            Start Research
          </Link>
          <div className="flex flex-wrap gap-3 mt-12">
            {BADGES.map(function (badge) {
              return (
                <span
                  key={badge}
                  className="font-[var(--font-mono)] text-xs px-3 py-1 rounded-full border border-[var(--border)] text-[var(--text-muted)]"
                >
                  {badge}
                </span>
              );
            })}
          </div>
        </div>

        {/* Right: illustration */}
        <div className="shrink-0 hidden md:block">
          <Image
            src="/RAG.png"
            alt="AI Research Engine illustration"
            width={540}
            height={440}
            priority
            className="object-contain drop-shadow-2xl"
            style={{ mixBlendMode: "lighten" }}
          />
        </div>
      </div>
    </section>
  );
}