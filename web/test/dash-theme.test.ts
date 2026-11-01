import { describe, it, expect, beforeEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { applyTheme, pickTheme, setMode, toggleDayNight, initThemes, selectTheme, getThemeState } from "../src/dash/theme";
import { olive, grass } from "./dash-fixtures";

beforeEach(() => { vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); localStorage.clear(); document.documentElement.removeAttribute("style"); });
const v = (k: string) => document.documentElement.style.getPropertyValue(`--dash-${k}`);

describe("theme", () => {
  it("applyTheme 把主題的每個鍵設成 --dash-<鍵>,dark 用 dark 那組", () => {
    applyTheme(olive, "light");
    for (const [k, val] of Object.entries(olive.light)) expect(v(k)).toBe(val);
    applyTheme(olive, "dark");
    for (const [k, val] of Object.entries(olive.dark)) expect(v(k)).toBe(val);
    expect(v("desk")).toBe("#1c1e14");
  });
  it("記住的主題 id 不在清單時用預設", () => {
    localStorage.setItem("hyenovel.theme", "gone");
    expect(pickTheme([olive, grass], "olive").id).toBe("olive");
    localStorage.setItem("hyenovel.theme", "grass");
    expect(pickTheme([olive, grass], "olive").id).toBe("grass");
  });
  it("selectTheme 立刻套用並記住", () => {
    initThemes([olive, grass], "olive");
    selectTheme("grass");
    expect(localStorage.getItem("hyenovel.theme")).toBe("grass");
    expect(v("accent")).toBe(grass[getThemeState().mode].accent);
  });
  it("主題套用後 --dash-accent 有值", () => {
    initThemes([olive, grass], "olive");
    expect(v("accent")).toBe(olive[getThemeState().mode].accent);
  });
  it("setMode 寫進第 1 批的 localStorage 鍵", () => {
    initThemes([olive, grass], "olive");
    setMode("dark");
    expect(localStorage.getItem("hyenovel.mode")).toBe("dark");
    expect(getThemeState().mode).toBe("dark");
    expect(v("desk")).toBe(olive.dark.desk);
  });
  it("toggleDayNight:系統暗+pref=system → light,再 → dark", () => {
    const mm = window.matchMedia;
    window.matchMedia = ((q: string) => ({ matches: q.includes("dark"), addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
    try {
      initThemes([olive, grass], "olive");
      expect(getThemeState().pref).toBe("system");
      expect(getThemeState().mode).toBe("dark");
      toggleDayNight();
      expect(getThemeState().mode).toBe("light");
      expect(localStorage.getItem("hyenovel.mode")).toBe("light");
      toggleDayNight();
      expect(getThemeState().mode).toBe("dark");
    } finally { window.matchMedia = mm; }
  });
  it("dash.css 不含色碼", () => {
    const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../src/dash/dash.css"), "utf8");
    expect(css).toContain("--dash-desk");
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  });
});
