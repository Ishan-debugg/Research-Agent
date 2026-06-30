"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useResearch } from "../../context/ResearchContext";
import { useUserProfile } from "../../context/UserProfileContext";
import BenchmarkExtracted from "../../components/BenchmarkExtracted";
import PapersExplorer from "../../components/PapersExplorer";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ResultsPage() {
  const research = useResearch();
  const profile = useUserProfile();
  const router = useRouter();

  const [techMatches, setTechMatches] = useState(null);
  const [techMatchLoading, setTechMatchLoading] = useState(false);

  useEffect(
    function () {
      if (!research.data) router.push("/search");
    },
    [research.data, router]
  );

  useEffect(
    function () {
      if (!research.data) return;
      if (!profile.techStack || profile.techStack.length === 0) return;

      let cancelled = false;
      setTechMatchLoading(true);

      const payload = {
        tech_stack: profile.techStack,
        papers: research.data.papers.map(function (p) {
          return { arxiv_id: p.arxiv_id, title: p.title, method: p.method, contribution: p.contribution };
        }),
      };

      fetch(API_URL + "/tech-match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) throw new Error("Tech match failed");
          return res.json();
        })
        .then(function (json) {
          if (!cancelled) setTechMatches(json.matches);
        })
        .catch(function () {
          if (!cancelled) setTechMatches(null);
        })
        .finally(function () {
          if (!cancelled) setTechMatchLoading(false);
        });

      return function () {
        cancelled = true;
      };
    },
    [research.data, profile.techStack]
  );

  if (!research.data) return null;

  const data = research.data;
  const techStackSet = profile.techStack && profile.techStack.length > 0;

  return (
    <main className="max-w-7xl mx-auto px-6 py-16">
      <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-3">
        [ research landscape ]
      </p>
      <h1 className="font-[var(--font-display)] text-2xl md:text-3xl mb-6">{research.query}</h1>

      <blockquote className="border-l-2 border-[var(--accent)] pl-5 italic text-[var(--text-muted)] leading-relaxed mb-10">
        {data.graph.summary}
      </blockquote>

      {data.graph.open_problems && data.graph.open_problems.length > 0 && (
        <div className="mb-14">
          <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--text-muted)] mb-3">Open problems</h2>
          <div className="flex flex-wrap gap-2">
            {data.graph.open_problems.map(function (p) {
              return (
                <span key={p} className="text-xs px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-muted)]">
                  {p}
                </span>
              );
            })}
          </div>
        </div>
      )}

      <h2 className="font-[var(--font-display)] text-xl mb-6">Benchmark Extracted</h2>
      <div className="mb-14">
        <BenchmarkExtracted papers={data.papers} />
      </div>

      <h2 className="font-[var(--font-display)] text-xl mb-1">Papers</h2>
      <p className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] mb-6 uppercase tracking-widest">Ranked by relevance · select a paper to view details</p>
      <PapersExplorer
        papers={data.papers}
        techMatches={techMatches}
        techStackSet={techStackSet}
        techMatchLoading={techMatchLoading}
      />

      <div className="mt-16 text-center">
        <Link
          href="/graph"
          className="inline-block px-6 py-2.5 rounded-md bg-[var(--accent)] text-[var(--bg)] font-medium hover:opacity-90 transition-opacity"
        >
          View knowledge graph
        </Link>
      </div>
    </main>
  );
}