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

const MAX_CHARS = 500;
const MIN_CHARS = 3;

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const research = useResearch();
  const router = useRouter();

  const charCount = query.length;
  const isOverLimit = charCount > MAX_CHARS;
  const isUnderLimit = charCount > 0 && charCount < MIN_CHARS;
  const isValid = !isOverLimit && !isUnderLimit && query.trim().length > 0;

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!isValid) return;
    research.startSearch(trimmed);
    router.push("/processing");
  }

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
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={function (e) {
              setQuery(e.target.value);
            }}
            placeholder="e.g. retrieval-augmented generation"
            className={`w-full px-4 py-3 rounded-md bg-[var(--surface)] border text-sm focus:outline-none transition-colors pr-16 ${
              isOverLimit ? "border-[var(--bad)] focus:border-[var(--bad)]" : "border-[var(--border)] focus:border-[var(--accent)]"
            }`}
            autoFocus
          />
          {/* Character counter */}
          <div
            className={`absolute right-3 top-1/2 -translate-y-1/2 font-[var(--font-mono)] text-[10px] ${
              isOverLimit ? "text-[var(--bad)]" : "text-[var(--text-muted)]"
            }`}
          >
            {charCount > 0 && `${charCount}/${MAX_CHARS}`}
          </div>
        </div>
        
        {/* Validation messages */}
        {isOverLimit && (
          <p className="text-xs text-[var(--bad)] mt-2 font-[var(--font-mono)]">
            Query exceeds the {MAX_CHARS} character limit.
          </p>
        )}
        {isUnderLimit && (
          <p className="text-xs text-[var(--bad)] mt-2 font-[var(--font-mono)]">
            Query must be at least {MIN_CHARS} characters.
          </p>
        )}

        <button
          type="submit"
          disabled={!isValid}
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