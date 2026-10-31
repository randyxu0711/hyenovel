import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { applyTheme, pickTheme, nextPref, cycleMode, initThemes, selectTheme, getThemeState } from "../src/dash/theme";
import { olive, grass } from "./dash-fixtures";

beforeEach(() => { localStorage.clear(); document.documentElement.removeAttribute("style"); });
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
  it("主題循環 system→light→dark→system 並記住", () => {
    expect(nextPref("system")).toBe("light");
    expect(nextPref("light")).toBe("dark");
    expect(nextPref("dark")).toBe("system");
    initThemes([olive, grass], "olive");
    cycleMode();
    expect(getThemeState().pref).toBe("light");
    expect(localStorage.getItem("hyenovel.mode")).toBe("light");
    cycleMode();
    expect(getThemeState().mode).toBe("dark");
    expect(v("desk")).toBe(olive.dark.desk);
  });
  it("selectTheme 立刻套用並記住", () => {
    initThemes([olive, grass], "olive");
    selectTheme("grass");
    expect(localStorage.getItem("hyenovel.theme")).toBe("grass");
    expect(v("enamel")).toBe(grass[getThemeState().mode].enamel);
  });
  it("dash.css 不含色碼", () => {
    const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../src/dash/dash.css"), "utf8");
    expect(css).toContain("--dash-desk");
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  });
});
