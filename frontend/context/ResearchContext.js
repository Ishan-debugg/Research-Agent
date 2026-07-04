"use client";

import { createContext, useContext, useState, useCallback, useRef } from "react";
import { saveHistoryEntry } from "../lib/historyStore";

const ResearchContext = createContext(null);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

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
  const watchdogRef = useRef(null); // timeout handle for SSE stall detection

  // Reset the 90-second watchdog timer. Called every time an SSE event arrives.
  function _resetWatchdog(reject) {
    if (watchdogRef.current) clearTimeout(watchdogRef.current);
    watchdogRef.current = setTimeout(() => {
      reject(new Error(
        "No response from server for 90 seconds. The pipeline may have stalled — please try again."
      ));
    }, 90_000);
  }

  const startSearch = useCallback(async function (q) {
    // Cancel any previous in-flight stream
    if (abortRef.current) abortRef.current.abort();
    if (watchdogRef.current) clearTimeout(watchdogRef.current);

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

    // Inner function: connect to SSE and read until done.
    // Returns true if complete, false if we should reconnect once.
    async function _consumeStream(isRetry) {
      try {
        const fetchHeaders = {};
        if (API_KEY) fetchHeaders["X-API-Key"] = API_KEY;

        const res = await fetch(
          API_URL + "/search/stream?query=" + encodeURIComponent(q),
          { signal: controller.signal, headers: fetchHeaders }
        );

        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          if (res.status === 429) throw new Error("Too many requests — please wait a moment before searching again.");
          if (res.status === 504) throw new Error(detail.detail || "The pipeline timed out (>120s). Try a more specific query.");
          if (res.status === 401) throw new Error("Unauthorized. Check your API key configuration.");
          throw new Error(detail.detail || "Request failed (" + res.status + ")");
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let receivedResult = false;

        // Start the 90-second watchdog
        await new Promise((resolve, reject) => {
          _resetWatchdog(reject);

          (async () => {
            try {
              while (true) {
                const { done, value } = await reader.read();
                if (done) { resolve(); break; }

                _resetWatchdog(reject); // reset timer on each chunk received
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop();

                let eventType = null;
                let eventData = null;

                for (const line of lines) {
                  if (line.startsWith("event: ")) {
                    eventType = line.slice(7).trim();
                  } else if (line.startsWith("data: ")) {
                    try { eventData = JSON.parse(line.slice(6)); } catch { /* ignore */ }
                  } else if (line === "" && eventType && eventData !== null) {
                    if (eventType === "stage") {
                      setLiveStage(eventData.stage);
                      setLiveMessage(eventData.message || "");
                      setLiveProgress(eventData.progress || 0);
                      if (eventData.elapsed != null) setLiveElapsed(eventData.elapsed);
                    } else if (eventType === "result") {
                      const json = eventData.data;
                      setData(json);
                      setStatus("done");
                      receivedResult = true;
                      saveHistoryEntry({
                        id: Date.now().toString(),
                        query: q,
                        date: new Date().toISOString(),
                        summary: json.graph?.summary || "",
                        data: json,
                      });
                    } else if (eventType === "error") {
                      reject(new Error(eventData.message || "Pipeline error"));
                      return;
                    }
                    eventType = null;
                    eventData = null;
                  }
                }
              }
            } catch (e) {
              reject(e);
            }
          })();
        });

        if (watchdogRef.current) clearTimeout(watchdogRef.current);
        return receivedResult;
      } catch (err) {
        if (watchdogRef.current) clearTimeout(watchdogRef.current);
        throw err;
      }
    }

    try {
      const complete = await _consumeStream(false);
      // If stream ended without a result event (network drop), retry once
      if (!complete) {
        setLiveMessage("Connection dropped — reconnecting...");
        await _consumeStream(true);
      }
    } catch (err) {
      if (err.name === "AbortError") return;
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
