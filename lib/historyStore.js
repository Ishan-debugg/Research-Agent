const KEY = "research-copilot-history";
const MAX_ENTRIES = 20;

export function getHistory() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

export function saveHistoryEntry(entry) {
  if (typeof window === "undefined") return;
  try {
    const existing = getHistory();
    const updated = [entry].concat(existing).slice(0, MAX_ENTRIES);
    window.localStorage.setItem(KEY, JSON.stringify(updated));
  } catch (e) {
    // localStorage can fail in private mode / quota limits - history is non-critical
  }
}

export function clearHistory() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}