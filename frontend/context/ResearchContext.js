"use client";

import { createContext, useContext, useState, useCallback, useRef } from "react";
import { saveHistoryEntry } from "../lib/historyStore";

const ResearchContext = createContext(null);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function ResearchProvider({ children }) {
  const [query, setQuery]   = useState("");
  const [status, setStatus] = useState("idle");
  const [data, setData]     = useState(null);
  const [error, setError]   = useState(null);

  // SSE live progress state
  const [liveStage, setLiveStage]     = useState(null);   // current stage name
  const [liveMessage, setLiveMessage] = useState("");     // human-readable message
  const [liveProgress, setLiveProgress] = useState(0);   // 1-5
  const [liveElapsed, setLiveElapsed]   = useState(null); // seconds for last stage

  // Allow abort of in-flight SSE stream
  const abortRef = useRef(null);

  const startSearch = useCallback(async function (q) {
    // Cancel any previous in-flight stream
    if (abortRef.current) abortRef.current.abort();

    const controller = new AbortController();
    abortRef.current = controller;

    setQuery(q);
    setStatus("loading");
    setError(null);
    setData(null);
    setLiveStage(null);
    setLiveMessage("");
    setLiveProgress(0);
    setLiveElapsed(null);

    try {
      // Use /search/stream to get real-time SSE progress
      const res = await fetch(
        API_URL + "/search/stream?query=" + encodeURIComponent(q),
        { signal: controller.signal }
      );

      // Surface clean HTTP errors immediately (429, 422, 504, etc.)
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        if (res.status === 429) {
          throw new Error("Too many requests — please wait a moment before searching again.");
        }
        if (res.status === 504) {
          throw new Error(
            detail.detail ||
            "The pipeline timed out (>120s). Try a more specific query."
          );
        }
        if (res.status === 401) {
          throw new Error("Unauthorized. Check your API key configuration.");
        }
        throw new Error(detail.detail || "Request failed (" + res.status + ")");
      }

      // SSE stream — read line by line
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep incomplete last line in buffer

        let eventType = null;
        let eventData = null;

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            try {
              eventData = JSON.parse(line.slice(6));
            } catch {
              // ignore malformed data lines
            }
          } else if (line === "" && eventType && eventData !== null) {
            // Dispatch event
            if (eventType === "stage") {
              setLiveStage(eventData.stage);
              setLiveMessage(eventData.message || "");
              setLiveProgress(eventData.progress || 0);
              if (eventData.elapsed != null) setLiveElapsed(eventData.elapsed);
            } else if (eventType === "result") {
              const json = eventData.data;
              setData(json);
              setStatus("done");
              saveHistoryEntry({
                id: Date.now().toString(),
                query: q,
                date: new Date().toISOString(),
                summary: json.graph?.summary || "",
                data: json,
              });
            } else if (eventType === "error") {
              throw new Error(eventData.message || "Pipeline error");
            }

            // Reset for next event pair
            eventType = null;
            eventData = null;
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") return; // user navigated away — silent
      setError(err.message || "Something went wrong");
      setStatus("error");
    }
  }, []);

  const loadFromHistory = useCallback(function (entry) {
    setQuery(entry.query);
    setData(entry.data);
    setStatus("done");
    setError(null);
    setLiveStage(null);
    setLiveMessage("");
    setLiveProgress(0);
  }, []);

  const reset = useCallback(function () {
    if (abortRef.current) abortRef.current.abort();
    setStatus("idle");
    setData(null);
    setError(null);
    setQuery("");
    setLiveStage(null);
    setLiveMessage("");
    setLiveProgress(0);
    setLiveElapsed(null);
  }, []);

  const value = {
    query,
    status,
    data,
    error,
    liveStage,
    liveMessage,
    liveProgress,
    liveElapsed,
    startSearch,
    loadFromHistory,
    reset,
  };

  return <ResearchContext.Provider value={value}>{children}</ResearchContext.Provider>;
}

export function useResearch() {
  const ctx = useContext(ResearchContext);
  if (!ctx) throw new Error("useResearch must be used within ResearchProvider");
  return ctx;
}
