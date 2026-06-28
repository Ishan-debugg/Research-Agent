"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "../../context/ResearchContext";
import PaperCard from "../../components/PaperCard";
import BenchmarkTable from "../../components/BenchmarkTable";

export default function ResultsPage() {
  const research = useResearch();
  const router = useRouter();

  useEffect(
    function () {
      if (!research.data) router.push("/search");
    },
    [research.data, router]
  );

  if (!research.data) return null;

  const data = research.data;

  return (
    <main className="max-w-4xl mx-auto px-6 py-16">
      <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-3">
        [ research landscape ]
      </p>
      <h1 className="font-[var(--font-display)] text-2xl md:text-3xl mb-6">
        {research.query}
      </h1>

      <blockquote className="border-l-2 border-[var(--accent)] pl-5 italic text-[var(--text-muted)] leading-relaxed mb-10">
        {data.graph.summary}
      </blockquote>

      {data.graph.open_problems && data.graph.open_problems.length > 0 && (
        <div className="mb-16">
          <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--text-muted)] mb-3">
            Open problems
          </h2>
          <div className="flex flex-wrap gap-2">
            {data.graph.open_problems.map(function (p) {
              return (
                <span
                  key={p}
                  className="text-xs px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-muted)]"
                >
                  {p}
                </span>
              );
            })}
          </div>
        </div>
      )}

      <h2 className="font-[var(--font-display)] text-xl mb-6">Papers</h2>
      <div className="space-y-5 mb-16">
        {data.papers.map(function (paper) {
          return <PaperCard key={paper.arxiv_id} paper={paper} />;
        })}
      </div>

      <h2 className="font-[var(--font-display)] text-xl mb-6">
        Benchmark Extracted
      </h2>
      <BenchmarkTable papers={data.papers} />

      <div className="mt-16 text-center">
        
          <a href="/graph"
          className="inline-block px-6 py-2.5 rounded-md bg-[var(--accent)] text-[var(--bg)] font-medium hover:opacity-90 transition-opacity"
        >
          View knowledge graph
        </a>
      </div>
    </main>
  );
}