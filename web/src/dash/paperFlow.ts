import { useSyncExternalStore } from "react";

/** 稿的排法:直排(v)/ 橫排(h)。存 localStorage;中文稿預設直排。稿頂與設定共用這一份。 */
export type PaperFlow = "v" | "h";
export const PAPER_FLOW_KEY = "hyenovel.paperFlow";

export function loadPaperFlow(): PaperFlow {
  try { return localStorage.getItem(PAPER_FLOW_KEY) === "h" ? "h" : "v"; } catch { return "v"; }
}

let flow: PaperFlow = loadPaperFlow();
const listeners = new Set<() => void>();

export function setPaperFlow(f: PaperFlow): void {
  try { localStorage.setItem(PAPER_FLOW_KEY, f); } catch { /* 存不了就只這次有效 */ }
  flow = f;
  listeners.forEach(l => l());
}

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
export const usePaperFlow = (): PaperFlow => useSyncExternalStore(subscribe, () => flow);
