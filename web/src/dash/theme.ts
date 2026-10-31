import { useSyncExternalStore } from "react";
import type { Character, Theme } from "./api";

export type ModePref = "system" | "light" | "dark";
export type Mode = "light" | "dark";

const THEME_KEY = "hyenovel.theme";
const MODE_KEY = "hyenovel.mode";
const NEXT: Record<ModePref, ModePref> = { system: "light", light: "dark", dark: "system" };

const read = (k: string): string | null => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* 存不了也照用 */ } };

export const nextPref = (p: ModePref): ModePref => NEXT[p];

export function loadModePref(): ModePref {
  const v = read(MODE_KEY);
  return v === "light" || v === "dark" || v === "system" ? v : "system";
}

export function resolveMode(pref: ModePref): Mode {
  if (pref !== "system") return pref;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** 記住的主題 id 對照清單;找不到(被刪、清單換了)用預設,預設也不在清單就用第一個。 */
export function pickTheme(themes: Theme[], defaultId: string): Theme {
  const saved = read(THEME_KEY);
  return themes.find(t => t.id === saved) ?? themes.find(t => t.id === defaultId) ?? themes[0];
}

/** 把該主題晝或夜的每個鍵設成根元素上的 --dash-<鍵>。 */
export function applyTheme(theme: Theme, mode: Mode): void {
  const root = document.documentElement;
  for (const [k, v] of Object.entries(theme[mode])) root.style.setProperty(`--dash-${k}`, v);
}

/** 目前陪讀者的招牌色(--dash-sig 毛色、--dash-sig-t 文字色),跟著角色資料走。 */
export function applySignature(c: Character, mode: Mode): void {
  const root = document.documentElement;
  root.style.setProperty("--dash-sig", c.colors[mode].fill);
  root.style.setProperty("--dash-sig-t", c.colors[mode].text);
}

// ── 狀態:使用者選的主題與明暗;resolved 是實際生效的晝/夜 ──
export type ThemeState = { themes: Theme[]; theme: Theme | null; pref: ModePref; mode: Mode };

let state: ThemeState = { themes: [], theme: null, pref: loadModePref(), mode: resolveMode(loadModePref()) };
const listeners = new Set<() => void>();

function commit(next: Partial<ThemeState>) {
  state = { ...state, ...next };
  state.mode = resolveMode(state.pref);
  if (state.theme) applyTheme(state.theme, state.mode);
  listeners.forEach(l => l());
}

export function initThemes(themes: Theme[], defaultId: string): void {
  commit({ themes, theme: pickTheme(themes, defaultId), pref: loadModePref() });
}
export function selectTheme(id: string): void {
  const theme = state.themes.find(t => t.id === id);
  if (!theme) return;
  write(THEME_KEY, id);
  commit({ theme });
}
export function cycleMode(): void {
  const pref = nextPref(state.pref);
  write(MODE_KEY, pref);
  commit({ pref });
}
export const getThemeState = () => state;

const subscribe = (l: () => void) => {
  listeners.add(l);
  // 跟系統時,系統明暗改了就重算
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  const onSys = () => { if (state.pref === "system") commit({}); };
  mq?.addEventListener?.("change", onSys);
  return () => { listeners.delete(l); mq?.removeEventListener?.("change", onSys); };
};
export const useThemeState = (): ThemeState => useSyncExternalStore(subscribe, getThemeState);
