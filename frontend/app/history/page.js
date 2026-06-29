"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "../../context/ResearchContext";
import { getHistory, clearHistory } from "../../lib/historyStore";

export default function HistoryPage() {
  const [entries, setEntries] = useState([]);
  const research = useResearch();
  const router = useRouter();

  useEffect(function () {
    setEntries(getHistory());
  }, []);

  function handleView(entry) {
    research.loadFromHistory(entry);
    router.push("/results");
  }

  function handleClear() {
    clearHistory();
    setEntries([]);
  }

  return (
    <main className="max-w-3xl mx-auto px-6 py-16">
      <div className="flex items-center justify-between mb-10">
        <h1 className="font-[var(--font-display)] text-2xl md:text-3xl">Search History</h1>
        {entries.length > 0 && (
          <button onClick={handleClear} className="text-xs text-[var(--text-muted)] hover:text-[var(--bad)] transition-colors">
            Clear history
          </button>
        )}
      </div>

      {entries.length === 0 && (
        <p className="text-sm text-[var(--text-muted)]">No searches yet. Run a search and it will show up here.</p>
      )}

      <div className="space-y-4">
        {entries.map(function (entry) {
          const date = new Date(entry.date);
          return (
            <div key={entry.id} className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-medium">{entry.query}</h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">
                    {date.toLocaleDateString() + " - " + date.toLocaleTimeString()}
                  </p>
                </div>
                <button
                  onClick={function () {
                    handleView(entry);
                  }}
                  className="text-xs px-3 py-1.5 rounded-full border border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors shrink-0"
                >
                  View Results
                </button>
              </div>
              <p className="text-sm text-[var(--text-muted)] mt-3 leading-relaxed">{entry.summary}</p>
            </div>
          );
        })}
      </div>
    </main>
  );
}