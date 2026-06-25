import { describe, it, expect } from "vitest";
import { buildBone } from "../src/lib/bone";
import type { VizData, VizNode } from "../src/types";

// 最小 fixture:3 個遞增張力的 beat(以 precedes 串)、1 個主題(復現 2)、1 個意象(復現 1)
const beat = (id: string, intensity: number): VizNode =>
  ({ id, type: "beat", label: id, note: "", intensity, evidence: [] });
const themeOrMotif = (id: string, type: "theme" | "motif", recur: number, pos: number): VizNode =>
  ({ id, type, label: id, note: "", intensity: null,
     evidence: Array.from({ length: recur }, () => ({ quote: "x", start: 0, end: 1, pos })) });

const viz: VizData = {
  slug: "s", title: "t",
  nodes: [
    beat("b1", 0.2), beat("b2", 0.5), beat("b3", 0.9),
    themeOrMotif("th", "theme", 2, 0.3),
    themeOrMotif("mo", "motif", 1, 0.6),
  ],
  edges: [
    { type: "precedes", from: "b1", to: "b2" },
    { type: "precedes", from: "b2", to: "b3" },
  ],
  colors: {}, cn: {}, diag: {}, feedback: null,
};

describe("buildBone — 資料驅動指紋", () => {
  it("脊椎 = 張力曲線:張力遞增 → 脊椎往上(y 變小)", () => {
    const { pts } = buildBone(viz);
    expect(pts.length).toBe(3);                         // 三個 beat
    expect(pts[2][1]).toBeLessThan(pts[0][1]);          // 末端比開頭高(y 小)
  });

  it("每個主題/意象一根肋;主題朝上、意象朝下", () => {
    const { ribs } = buildBone(viz);
    expect(ribs.length).toBe(2);
    const th = ribs.find(r => r.label === "th")!;
    const mo = ribs.find(r => r.label === "mo")!;
    expect(th.theme).toBe(true);
    expect(th.y2).toBeLessThan(th.y1);                  // 主題朝上
    expect(mo.theme).toBe(false);
    expect(mo.y2).toBeGreaterThan(mo.y1);               // 意象朝下
  });

  it("肋長隨復現次數遞增", () => {
    const { ribs } = buildBone(viz);
    const th = ribs.find(r => r.label === "th")!;       // 復現 2
    const mo = ribs.find(r => r.label === "mo")!;       // 復現 1
    const len = (r: typeof th) => Math.hypot(r.x2 - r.x1, r.y2 - r.y1);
    expect(len(th)).toBeGreaterThan(len(mo));
  });
});
