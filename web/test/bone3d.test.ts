import { describe, it, expect } from "vitest";
import { buildBone3D } from "../src/lib/bone3d";

describe("buildBone3D", () => {
  it("同一 seed 結果穩定", () => {
    expect(buildBone3D(42)).toEqual(buildBone3D(42));
  });
  it("脊椎 9 點;肋數 8..12;每根肋 tip≠base", () => {
    const b = buildBone3D(7);
    expect(b.spine.length).toBe(9);
    expect(b.ribs.length).toBeGreaterThanOrEqual(8);
    expect(b.ribs.length).toBeLessThanOrEqual(12);
    for (const rib of b.ribs) {
      const d = Math.hypot(rib.tip[0] - rib.base[0], rib.tip[1] - rib.base[1], rib.tip[2] - rib.base[2]);
      expect(d).toBeGreaterThan(0.4);
    }
  });
  it("不同 seed 給不同脊椎", () => {
    expect(buildBone3D(1).spine).not.toEqual(buildBone3D(2).spine);
  });
});
