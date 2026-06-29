"use client";

import { createContext, useContext, useState, useCallback } from "react";
import { saveHistoryEntry } from "../lib/historyStore";

const ResearchContext = createContext(null);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function ResearchProvider({ children }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("idle");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const startSearch = useCallback(async function (q) {
    setQuery(q);
    setStatus("loading");
    setError(null);
    setData(null);

    try {
      const res = await fetch(API_URL + "/search?query=" + encodeURIComponent(q));
      if (!res.ok) {
        const detail = await res.json().catch(function () {
          return {};
        });
        throw new Error(detail.detail || "Request failed (" + res.status + ")");
      }
      const json = await res.json();
      setData(json);
      setStatus("done");
      saveHistoryEntry({
        id: Date.now().toString(),
        query: q,
        date: new Date().toISOString(),
        summary: json.graph.summary,
        data: json,
      });
    } catch (err) {
      setError(err.message || "Something went wrong");
      setStatus("error");
    }
  }, []);

  const loadFromHistory = useCallback(function (entry) {
    setQuery(entry.query);
    setData(entry.data);
    setStatus("done");
    setError(null);
  }, []);

  const reset = useCallback(function () {
    setStatus("idle");
    setData(null);
    setError(null);
    setQuery("");
  }, []);

  const value = {
    query: query,
    status: status,
    data: data,
    error: error,
    startSearch: startSearch,
    loadFromHistory: loadFromHistory,
    reset: reset,
  };

  return <ResearchContext.Provider value={value}>{children}</ResearchContext.Provider>;
}

export function useResearch() {
  const ctx = useContext(ResearchContext);
  if (!ctx) {
    throw new Error("useResearch must be used within ResearchProvider");
  }
  return ctx;
}
