"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "../../context/ResearchContext";
import PipelinePreviewWindow from "../../components/PipelinePreviewWindow";

// Ordered pipeline steps shown in the step list.
const STEPS = [
  { key: "retrieving",   label: "Retrieve relevant papers from arXiv",  icon: "①" },
  { key: "reranking",    label: "Semantic rerank with CrossEncoder",     icon: "②" },
  { key: "downloading",  label: "Fetch paper text (abstract / PDF)",     icon: "③" },
  { key: "extracting",   label: "Structured extraction via Gemini",      icon: "④" },
  { key: "synthesizing", label: "Knowledge graph synthesis",             icon: "⑤" },
];

// Short labels for the timing pills
const STEP_SHORT_LABELS = ["arXiv", "Rerank", "Text", "Extract", "Graph"];

// Accent colors per stage (matches PipelinePreviewWindow)
const STEP_COLORS = ["#6ee7b7", "#93c5fd", "#c4b5fd", "#fbbf24", "#f472b6"];

// Map any stage name → parent step index
const STAGE_TO_INDEX = {
  retrieving: 0, retrieved:   0,
  reranking:  1, reranked:    1,
  downloading:2, downloaded:  2,
  extracting: 3, extracted:   3,
  synthesizing:4,synthesized: 4,
};

// "done" variant names — stage is complete when we see these
const DONE_STAGES = new Set(["retrieved","reranked","downloaded","extracted","synthesized"]);

export default function ProcessingPage() {
  const research = useResearch();
  const router   = useRouter();

  // Per-stage elapsed timings collected from SSE
  const [stageTimings, setStageTimings] = useState([]);
  const prevStageRef = useRef(null);

  // Collect timing when a "done" stage arrives with an elapsed value
  useEffect(function () {
    const stage   = research.liveStage;
    const elapsed = research.liveElapsed;
    if (!stage || !DONE_STAGES.has(stage) || elapsed == null) return;
    if (stage === prevStageRef.current) return;

    prevStageRef.current = stage;
    const idx   = STAGE_TO_INDEX[stage];
    const label = STEP_SHORT_LABELS[idx] ?? stage;

    setStageTimings(function (prev) {
      if (prev.some(function (t) { return t.label === label; })) return prev;
      return [...prev, { label, elapsed: String(elapsed), idx }];
    });
  }, [research.liveStage, research.liveElapsed]);

  // Reset on new search
  useEffect(function () {
    if (research.status === "loading") {
      setStageTimings([]);
      prevStageRef.current = null;
    }
  }, [research.status]);

  // Navigate when done; guard against landing without a search
  useEffect(function () {
    if (research.status === "done") {
      const t = setTimeout(function () { router.push("/results"); }, 500);
      return function () { clearTimeout(t); };
    }
    if (research.status === "idle") router.push("/search");
  }, [research.status, router]);

  const currentIndex = research.liveStage != null
    ? (STAGE_TO_INDEX[research.liveStage] ?? STEPS.length - 1)
    : -1;

  // ── Error state ─────────────────────────────────────────────────────────
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
        <p className="text-sm text-[var(--text-muted)] max-w-md mb-8">{research.error}</p>
        <button
          onClick={function () { router.push("/search"); }}
          className="px-6 py-2.5 rounded-md border border-[var(--border)] hover:border-[var(--accent)] transition-colors text-sm"
        >
          Try a different search
        </button>
      </main>
    );
  }

  // ── Loading / cache-hit state ────────────────────────────────────────────
  return (
    <main className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6 py-12">

      {/* Pipeline preview window (progress bar + timing pills) */}
      <PipelinePreviewWindow
        query={research.query}
        liveStage={research.liveStage}
        liveMessage={research.liveMessage}
        liveProgress={research.liveProgress}
        stageTimings={stageTimings}
        elapsedSeconds={research.elapsedSeconds}
      />

      {/* Query label */}
      <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-2">
        {'[ mapping "' + research.query + '" ]'}
      </p>

      {/* Cache badge — shown when result comes from cache */}
      {research.fromCache ? (
        <div className="flex items-center gap-2 mb-4 px-3 py-1.5 rounded-full border"
          style={{ borderColor:"#6ee7b7", background:"color-mix(in srgb,#6ee7b7 10%,transparent)" }}>
          <span style={{ color:"#6ee7b7" }} className="text-sm">⚡</span>
          <span className="font-[var(--font-mono)] text-xs uppercase tracking-widest" style={{ color:"#6ee7b7" }}>
            Served from cache
          </span>
        </div>
      ) : (
        <h1 className="font-[var(--font-display)] text-2xl md:text-3xl mb-6">
          Reading the literature
        </h1>
      )}

      {/* ── Per-stage real-time step list ───────────────────────────────── */}
      <ol className="w-full max-w-lg space-y-3">
        {STEPS.map(function (step, i) {
          const done   = i < currentIndex || research.status === "done";
          const active = i === currentIndex && research.status !== "done";
          const color  = STEP_COLORS[i];

          // Find elapsed time for this step
          const timing = stageTimings.find(function (t) { return t.idx === i; });

          return (
            <li key={step.key}
              className="flex items-center gap-3 rounded-lg px-4 py-3 transition-all duration-300"
              style={{
                background: active
                  ? `color-mix(in srgb, ${color} 8%, transparent)`
                  : done
                  ? `color-mix(in srgb, ${color} 4%, transparent)`
                  : "transparent",
                border: active
                  ? `1px solid color-mix(in srgb, ${color} 40%, transparent)`
                  : done
                  ? `1px solid color-mix(in srgb, ${color} 20%, transparent)`
                  : "1px solid var(--border)",
              }}
            >
              {/* Step number / check circle */}
              <span
                className="font-[var(--font-mono)] text-xs w-7 h-7 rounded-full flex items-center justify-center border shrink-0 transition-all duration-300"
                style={
                  done
                    ? { borderColor: color, background: color, color: "#000" }
                    : active
                    ? { borderColor: color, color: color }
                    : { borderColor: "var(--border)", color: "var(--text-muted)" }
                }
              >
                {done ? "✓" : i + 1}
              </span>

              {/* Label + live message */}
              <div className="flex flex-col flex-1 min-w-0">
                <span
                  className="text-sm transition-colors duration-300"
                  style={{ color: done || active ? "var(--text)" : "var(--text-muted)" }}
                >
                  {step.label}
                </span>
                {active && research.liveMessage && (
                  <span
                    className="text-[10px] font-[var(--font-mono)] animate-pulse truncate mt-0.5"
                    style={{ color }}
                  >
                    {research.liveMessage}
                  </span>
                )}
              </div>

              {/* Per-stage elapsed time — shown as soon as stage completes */}
              {timing ? (
                <span
                  className="font-[var(--font-mono)] text-xs tabular-nums shrink-0 px-2 py-0.5 rounded-full"
                  style={{
                    color,
                    background: `color-mix(in srgb, ${color} 15%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
                  }}
                >
                  {timing.elapsed === "0" ? "⚡ cached" : timing.elapsed + "s"}
                </span>
              ) : active ? (
                /* Live ticking timer for the currently-running stage */
                <span
                  className="font-[var(--font-mono)] text-xs tabular-nums shrink-0 animate-pulse"
                  style={{ color }}
                >
                  {research.elapsedSeconds.toFixed(1)}s…
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>

      {/* ── Footer status ─────────────────────────────────────────────────── */}
      <div className="mt-8 flex flex-col items-center gap-1">
        <p className="font-[var(--font-mono)] text-xs text-[var(--text-muted)]">
          {research.status === "done"
            ? `Done in ${research.totalElapsed ?? research.elapsedSeconds.toFixed(1)}s — opening results…`
            : research.fromCache
            ? "⚡ Results loaded from cache"
            : research.liveStage
            ? `Stage ${research.liveProgress || "?"} / 5  ·  ${research.elapsedSeconds.toFixed(1)}s elapsed`
            : "Connecting to pipeline…"}
        </p>
      </div>
    </main>
  );
}