import { useMemo, useSyncExternalStore } from "react";
import type { Work } from "./api";

const KEY = "hyenovel.seen";
const listeners = new Set<() => void>();

const readRaw = (): string => { try { return localStorage.getItem(KEY) ?? ""; } catch { return ""; } };
function parse(raw: string): Record<string, number> {
  try {
    const v = raw ? JSON.parse(raw) : {};
    return v && typeof v === "object" ? v : {};
  } catch { return {}; }
}
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };

/** 每篇作品「最後打開」的時間(epoch 秒,跟 den 的 updated_at 同單位)。所有使用者共享同一份。 */
export function useSeen() {
  const raw = useSyncExternalStore(subscribe, readRaw);
  const map = useMemo(() => parse(raw), [raw]);
  return {
    seen: (slug: string): number | null => (typeof map[slug] === "number" ? map[slug] : null),
    markSeen: (slug: string): void => {
      try { localStorage.setItem(KEY, JSON.stringify({ ...parse(readRaw()), [slug]: Date.now() / 1000 })); } catch { /* 存不了就不記 */ }
      listeners.forEach(l => l());
    },
  };
}

const BUSY = ["running", "notes-running"];

/** 沒打開過(null)不算新:第一次使用不會全亮。分析中永遠是 busy。 */
export function dotState(w: Work, seenAt: number | null): "fresh" | "busy" | "none" {
  if (BUSY.includes(String(w.state))) return "busy";
  return seenAt !== null && w.updated_at > seenAt ? "fresh" : "none";
}
