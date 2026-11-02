import { useState } from "react";

/** 書架兩態:展開(作品→局)/ 窄條(只剩圖示)。選擇存 localStorage,不跟畫面綁。 */
export type ShelfMode = "open" | "rail";
export const SHELF_KEY = "hyenovel.shelf";
export const SHELF_W: Record<ShelfMode, number> = { open: 244, rail: 56 };

function initial(): ShelfMode {
  let saved: string | null = null;
  try { saved = localStorage.getItem(SHELF_KEY); } catch { /* 讀不到 = 沒存過 */ }
  if (saved === "open" || saved === "rail") return saved;
  return window.innerWidth >= 1280 ? "open" : "rail";
}

export function useShelf(): { mode: ShelfMode; toggle: () => void } {
  const [mode, setMode] = useState<ShelfMode>(initial);
  const toggle = () => setMode(m => {
    const next = m === "open" ? "rail" : "open";
    try { localStorage.setItem(SHELF_KEY, next); } catch { /* 存不了就只這次有效 */ }
    return next;
  });
  return { mode, toggle };
}
