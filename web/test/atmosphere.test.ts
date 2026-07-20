import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// 大氣層(spec art-immersion §3B)守門:只測「我們的政策」——
// 背景單一正本在 --sky、冷底不得在各 css 複製貼上;顏色好不好看是眼睛的事,不測。
const src = (f: string) =>
  readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../src", f), "utf8");

describe("冷夜大氣", () => {
  it("theme.css 定義 --sky 並由 body 引用(背景單一正本)", () => {
    const theme = src("theme.css");
    expect(theme).toMatch(/--sky:/);
    expect(theme).toMatch(/body\{[^}]*background:\s*var\(--sky\)/s);
  });
  it("journey.css / lab.css 不再各自複製整片天(改吃 var(--sky))", () => {
    // 舊帳:.single / .lab / .sb 三處各留一份 radial-gradient(120% 90% …)
    for (const f of ["journey/journey.css", "lab/lab.css"])
      expect(src(f), `${f} 還有整片天的複本`).not.toMatch(/radial-gradient\(120% 90%/);
  });
  it("grain 覆層存在:tiled noise、pointer-events:none、極低 opacity", () => {
    const theme = src("theme.css");
    const m = /\.grain\{([^}]*)\}/s.exec(theme);
    expect(m, "theme.css 缺 .grain").not.toBeNull();
    expect(m![1]).toMatch(/pointer-events:\s*none/);
    expect(m![1]).toMatch(/feTurbulence/);
    const op = /opacity:\s*(0?\.\d+)/.exec(m![1]);
    expect(parseFloat(op![1]), "grain 該是質感不是雜訊").toBeLessThanOrEqual(0.08);
  });
});
