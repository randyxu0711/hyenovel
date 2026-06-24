import { describe, it, expect } from "vitest";
import { buildBone } from "../src/lib/bone";

describe("buildBone", () => {
  it("同一 seed 結果穩定", () => {
    expect(buildBone(42)).toEqual(buildBone(42));
  });
  it("肋骨數在 6..9,脊椎 path 以 M 開頭", () => {
    const b = buildBone(7);
    expect(b.ribs.length).toBeGreaterThanOrEqual(6);
    expect(b.ribs.length).toBeLessThanOrEqual(9);
    expect(b.d.startsWith("M")).toBe(true);
  });
  it("不同 seed 給不同骨架", () => {
    expect(buildBone(1).d).not.toBe(buildBone(2).d);
  });
});
