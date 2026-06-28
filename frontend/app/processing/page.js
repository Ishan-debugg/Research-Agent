"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "../../context/ResearchContext";

const STEPS = [
  { label: "Retrieve relevant papers", seconds: 4 },
  { label: "Semantic rerank", seconds: 4 },
  { label: "Extract text from PDFs", seconds: 18 },
  { label: "Synthesize answer", seconds: 9 },
];

const TOTAL_SECONDS = STEPS.reduce(function (sum, s) {
  return sum + s.seconds;
}, 0);

export default function ProcessingPage() {
  const research = useResearch();
  const router = useRouter();
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef(Date.now());

  useEffect(function () {
    const interval = setInterval(function () {
      setElapsed((Date.now() - startedAt.current) / 1000);
    }, 200);
    return function () {
      clearInterval(interval);
    };
  }, []);

  useEffect(
    function () {
      if (research.status === "done") {
        const timeout = setTimeout(function () {
          router.push("/results");
        }, 500);
        return function () {
          clearTimeout(timeout);
        };
      }
      if (research.status === "idle") {
        router.push("/search");
      }
    },
    [research.status, router]
  );

  let cumulative = 0;
  let activeIndex = STEPS.length - 1;
  for (let i = 0; i < STEPS.length; i++) {
    cumulative += STEPS[i].seconds;
    if (elapsed < cumulative) {
      activeIndex = i;
      break;
    }
  }

  const remaining = Math.max(0, Math.round(TOTAL_SECONDS - elapsed));
  const overEstimate = elapsed > TOTAL_SECONDS;

  if (research.status === "error") {
    return (
      <main className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6 text-center">
        <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--bad)] mb-4">
          [ pipeline failed ]
        </p>
        <h1 className="font-[var(--font-display)] text-2xl mb-3">
          Something went wrong
        </h1>
        <p className="text-sm text-[var(--text-muted)] max-w-md mb-8">
          {research.error}
        </p>
        <button
          onClick={function () {
            router.push("/search");
          }}
          className="px-6 py-2.5 rounded-md border border-[var(--border)] hover:border-[var(--accent)] transition-colors text-sm"
        >
          Try a different search
        </button>
      </main>
    );
  }

  return (
    <main className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-6">
      <p className="font-[var(--font-mono)] text-xs uppercase tracking-widest text-[var(--accent)] mb-2">
        {'[ mapping "' + research.query + '" ]'}
      </p>
      <h1 className="font-[var(--font-display)] text-2xl md:text-3xl mb-12">
        Reading the literature
      </h1>

      <ol className="w-full max-w-md space-y-5">
        {STEPS.map(function (step, i) {
          const done = i < activeIndex || research.status === "done";
          const active = i === activeIndex && research.status !== "done";
          let circleClass =
            "font-[var(--font-mono)] text-xs w-7 h-7 rounded-full flex items-center justify-center border ";
          if (done) {
            circleClass +=
              "border-[var(--accent)] bg-[var(--accent)] text-[var(--bg)]";
          } else if (active) {
            circleClass += "border-[var(--accent)] text-[var(--accent)] animate-pulse";
          } else {
            circleClass += "border-[var(--border)] text-[var(--text-muted)]";
          }
          const labelClass =
            done || active ? "text-[var(--text)]" : "text-[var(--text-muted)]";

          return (
            <li key={step.label} className="flex items-center gap-4">
              <span className={circleClass}>{done ? "OK" : i + 1}</span>
              <span className={labelClass}>{step.label}</span>
            </li>
          );
        })}
      </ol>

      <p className="font-[var(--font-mono)] text-xs text-[var(--text-muted)] mt-12">
        {research.status === "done"
          ? "Done, opening results..."
          : overEstimate
          ? "Still working - " + Math.round(elapsed) + "s elapsed"
          : "Estimated time remaining: ~" + remaining + "s"}
      </p>
    </main>
  );
}