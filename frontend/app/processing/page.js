"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "../../context/ResearchContext";
import PipelinePreviewWindow from "../../components/PipelinePreviewWindow";

// The ordered stages the SSE stream emits — used to drive the step list.
// "stage" values match what the backend sends in the `event: stage` payload.
const STEPS = [
  { key: "retrieving",  label: "Retrieve relevant papers from arXiv" },
  { key: "reranking",   label: "Semantic rerank with CrossEncoder" },
  { key: "downloading", label: "Download & parse PDFs" },
  { key: "extracting",  label: "Structured extraction via Gemini" },
  { key: "synthesizing",label: "Knowledge graph synthesis" },
];

// Map any "done" sub-stage back to its parent step index so we can mark it complete
const STAGE_TO_INDEX = {
  retrieving:   0,
  retrieved:    0,
  reranking:    1,
  reranked:     1,
  downloading:  2,
  downloaded:   2,
  extracting:   3,
  extracted:    3,
  synthesizing: 4,
  synthesized:  4,
};

export default function ProcessingPage() {
  const research = useResearch();
  const router   = useRouter();

  // Redirect once done or if somehow we land here without a search in progress
  useEffect(function () {
    if (research.status === "done") {
      const t = setTimeout(function () { router.push("/results"); }, 400);
      return function () { clearTimeout(t); };
    }
    if (research.status === "idle") {
      router.push("/search");
    }
  }, [research.status, router]);

  // Derive which step is active from the live SSE stage name
  const currentIndex = research.liveStage != null
    ? (STAGE_TO_INDEX[research.liveStage] ?? STEPS.length - 1)
    : -1;

  // ── Error state ──────────────────────────────────────────────────────────
  if (research.status === "error") {
    const is504 = research.error && research.error.includes("timed out");
    const is429 = research.error && research.error.includes("Too many");

    return (
      <main className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6 text-center">
        <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--bad)] mb-4">
          {is504 ? "[ timeout ]" : is429 ? "[ rate limited ]" : "[ pipeline failed ]"}
        </p>
        <h1 className="font-[var(--font-display)] text-2xl mb-3">
          {is504 ? "Pipeline timed out" : is429 ? "Slow down!" : "Something went wrong"}
        </h1>
        <p className="text-sm text-[var(--text-muted)] max-w-md mb-8">
          {research.error}
        </p>
        <button
          onClick={function () { router.push("/search"); }}
          className="px-6 py-2.5 rounded-md border border-[var(--border)] hover:border-[var(--accent)] transition-colors text-sm"
        >
          Try a different search
        </button>
      </main>
    );
  }

  // ── Normal loading state ─────────────────────────────────────────────────
  return (
    <main className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6 py-12">
      <PipelinePreviewWindow
        query={research.query}
        liveStage={research.liveStage}
        liveMessage={research.liveMessage}
        liveProgress={research.liveProgress}
      />

      <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-2">
        {'[ mapping "' + research.query + '" ]'}
      </p>
      <h1 className="font-[var(--font-display)] text-2xl md:text-3xl mb-12">
        Reading the literature
      </h1>

      {/* ── Step list ── */}
      <ol className="w-full max-w-md space-y-5">
        {STEPS.map(function (step, i) {
          const done   = i < currentIndex || research.status === "done";
          const active = i === currentIndex && research.status !== "done";
          const pending = i > currentIndex && research.status !== "done";

          const circleBase = "font-[var(--font-mono)] text-xs w-7 h-7 rounded-full flex items-center justify-center border shrink-0 transition-all duration-300 ";
          const circleClass = done
            ? circleBase + "border-[var(--accent)] bg-[var(--accent)] text-[var(--bg)]"
            : active
            ? circleBase + "border-[var(--accent)] text-[var(--accent)] animate-pulse"
            : circleBase + "border-[var(--border)] text-[var(--text-muted)]";

          return (
            <li key={step.key} className="flex items-start gap-4">
              <span className={circleClass}>
                {done ? "✓" : i + 1}
              </span>
              <div className="flex flex-col gap-0.5">
                <span className={
                  done || active
                    ? "text-[var(--text)] text-sm transition-colors duration-300"
                    : "text-[var(--text-muted)] text-sm transition-colors duration-300"
                }>
                  {step.label}
                </span>
                {/* Show live backend message under active step */}
                {active && research.liveMessage && (
                  <span className="text-xs text-[var(--accent)] font-[var(--font-mono)] animate-pulse">
                    {research.liveMessage}
                  </span>
                )}
                {/* Show timing when step just completed */}
                {done && i === currentIndex - 1 && research.liveElapsed != null && (
                  <span className="text-xs text-[var(--text-muted)] font-[var(--font-mono)]">
                    {research.liveElapsed}s
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {/* ── Status footer ── */}
      <p className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] mt-12 text-center max-w-sm">
        {research.status === "done"
          ? "Done — opening results…"
          : research.liveStage
          ? "Stage " + (research.liveProgress || "?") + " of 5 · live from backend"
          : "Connecting to pipeline…"}
      </p>
    </main>
  );
}