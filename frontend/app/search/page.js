"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "../../context/ResearchContext";

const EXAMPLES = [
  "retrieval-augmented generation",
  "diffusion policy learning",
  "mixture of experts routing",
  "long-context transformers",
  "RLHF alignment",
];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const research = useResearch();
  const router = useRouter();

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    research.startSearch(trimmed);
    router.push("/processing");
  }

  /* ── Improvement: auto-submit on chip click ── */
  function handleExample(topic) {
    setQuery(topic);
    research.startSearch(topic);
    router.push("/processing");
  }

  return (
    <main className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6">
      <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-4">
        [ enter a topic ]
      </p>
      <h1 className="font-[var(--font-display)] text-3xl md:text-4xl text-center max-w-lg mb-10">
        What field do you want mapped?
      </h1>

      <form onSubmit={handleSubmit} className="w-full max-w-xl">
        <input
          type="text"
          value={query}
          onChange={function (e) {
            setQuery(e.target.value);
          }}
          placeholder="e.g. retrieval-augmented generation"
          className="w-full px-4 py-3 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
          autoFocus
        />
        <button
          type="submit"
          disabled={!query.trim()}
          className="w-full mt-3 py-3 rounded-md bg-[var(--accent)] text-[var(--bg)] font-medium tracking-wide disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
        >
          RESEARCH COPILOT
        </button>
      </form>

      <p className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] mt-8 mb-3 uppercase tracking-widest">
        — or try one of these —
      </p>
      <div className="flex flex-wrap justify-center gap-2 max-w-xl">
        {EXAMPLES.map(function (topic) {
          return (
            <button
              key={topic}
              onClick={function () {
                handleExample(topic);
              }}
              className="text-xs px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
            >
              {topic} ↗
            </button>
          );
        })}
      </div>
    </main>
  );
}