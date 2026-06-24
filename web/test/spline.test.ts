import { describe, it, expect } from "vitest";
import { spline, beatsToPoints } from "../src/lib/spline";

describe("spline", () => {
  it("beatsToPoints 等距分布 x、強度映射 y", () => {
    const pts = beatsToPoints([0, 1], 0, 100, 100, 80);
    expect(pts[0]).toEqual([0, 100]);     // intensity 0 → 底
    expect(pts[1]).toEqual([100, 20]);    // intensity 1 → 100-80
  });
  it("spline 以 M 開頭、含 C 段", () => {
    const d = spline([[0,0],[10,10],[20,0]]);
    expect(d.startsWith("M0,0")).toBe(true);
    expect(d).toContain("C");
  });
});
