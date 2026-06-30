"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useResearch } from "../../context/ResearchContext";
import { useUserProfile } from "../../context/UserProfileContext";
import BenchmarkExtracted from "../../components/BenchmarkExtracted";
import PapersExplorer from "../../components/PapersExplorer";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Feature: Export helpers ── */
function exportMarkdown(query, data) {
  const lines = [];
  lines.push("# Research Landscape: " + query + "\n");
  lines.push("> " + (data.graph.summary || "") + "\n");

  if (data.graph.open_problems && data.graph.open_problems.length > 0) {
    lines.push("## Open Problems\n");
    data.graph.open_problems.forEach(function (p) { lines.push("- " + p); });
    lines.push("");
  }

  lines.push("## Papers\n");
  data.papers.forEach(function (p, i) {
    lines.push("### " + (i + 1) + ". " + p.title);
    lines.push("**Relevance:** " + (p.relevance_score || 0) + "% | **Year:** " + (p.year || "—") + " | **Authors:** " + ((p.authors || []).slice(0, 3).join(", ") || "—"));
    lines.push("");
    if (p.problem)           lines.push("**Problem:** " + p.problem);
    if (p.method)            lines.push("**Method:** " + p.method);
    if (p.results)           lines.push("**Results:** " + p.results);
    if (p.contribution)      lines.push("**Contribution:** " + p.contribution);
    if (p.limitations)       lines.push("**Limitations:** " + p.limitations);
    if (p.real_world_impact) lines.push("**Impact:** " + p.real_world_impact);
    lines.push("");
    if (p.pdf_url) lines.push("[View on arXiv](" + p.pdf_url + ")");
    lines.push("\n---\n");
  });

  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "research-" + query.replace(/\s+/g, "-").toLowerCase() + ".md";
  a.click();
  URL.revokeObjectURL(url);
}

function exportCSV(query, data) {
  function esc(v) {
    return '"' + String(v || "").replace(/"/g, '""') + '"';
  }
  const headers = ["#", "Title", "Authors", "Year", "Relevance%", "Problem", "Method", "Dataset", "Results", "Contribution", "Limitations", "arXiv URL"];
  const rows = data.papers.map(function (p, i) {
    return [
      i + 1,
      esc(p.title),
      esc((p.authors || []).slice(0, 3).join("; ")),
      p.year || "",
      p.relevance_score || 0,
      esc(p.problem),
      esc(p.method),
      esc(p.dataset),
      esc(p.results),
      esc(p.contribution),
      esc(p.limitations),
      p.pdf_url || "",
    ].join(",");
  });
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "research-" + query.replace(/\s+/g, "-").toLowerCase() + ".csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function ResultsPage() {
  const research = useResearch();
  const profile = useUserProfile();
  const router = useRouter();

  const [techMatches, setTechMatches] = useState(null);
  const [techMatchLoading, setTechMatchLoading] = useState(false);
  const [exporting, setExporting] = useState(null); // "md" | "csv" | null

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

  function handleExportMD() {
    setExporting("md");
    setTimeout(function () {
      exportMarkdown(research.query, data);
      setExporting(null);
    }, 100);
  }

  function handleExportCSV() {
    setExporting("csv");
    setTimeout(function () {
      exportCSV(research.query, data);
      setExporting(null);
    }, 100);
  }

  return (
    <main className="max-w-7xl mx-auto px-6 py-16">
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-3">
            [ research landscape ]
          </p>
          <h1 className="font-[var(--font-display)] text-2xl md:text-3xl">{research.query}</h1>
        </div>

        {/* ── Feature: Export buttons ── */}
        <div className="flex items-center gap-2 shrink-0 mt-2">
          <button
            onClick={handleExportMD}
            disabled={exporting === "md"}
            className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-50"
          >
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 2v8M4 7l3 3 3-3" /><path d="M2 12h10" />
            </svg>
            {exporting === "md" ? "Exporting…" : "Export MD"}
          </button>
          <button
            onClick={handleExportCSV}
            disabled={exporting === "csv"}
            className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-50"
          >
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <rect x="1" y="1" width="12" height="12" rx="2" /><path d="M1 5h12M5 1v12" />
            </svg>
            {exporting === "csv" ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>

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
      <p className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] mb-6 uppercase tracking-widest">
        Ranked by relevance · ↑↓ keys to navigate · hover to preview · ⊕ to compare
      </p>
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