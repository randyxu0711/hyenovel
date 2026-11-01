import { describe, it, expect } from "vitest";
import { spotField } from "../src/dash/spots";

const N = 480;
describe("spotField", () => {
  const a = spotField(N, 8, 11);
  it("同 seed 結果相同,不同 seed 不同", () => {
    expect(spotField(N, 8, 11)).toEqual(a);
    expect(spotField(N, 8, 12)).not.toEqual(a);
    expect(a.length).toBeGreaterThan(0);
  });
  it("所有點在 [0,n)、半徑 ∈ [0.6, 2.1]", () => {
    for (const p of a) {
      expect(p.x).toBeGreaterThanOrEqual(0); expect(p.x).toBeLessThan(N);
      expect(p.y).toBeGreaterThanOrEqual(0); expect(p.y).toBeLessThan(N);
      expect(p.r).toBeGreaterThanOrEqual(0.6); expect(p.r).toBeLessThanOrEqual(2.1);
    }
  });
  it("四邊環繞:靠邊的斑點在對邊也有點", () => {
    const near = a.filter(p => p.x < 20);
    const far = a.filter(p => p.x > N - 20);
    expect(near.length).toBeGreaterThan(0);
    expect(far.length).toBeGreaterThan(0);
    const ys = (l: typeof a) => new Set(l.map(p => p.y));
    expect([...ys(near)].some(y => ys(far).has(y))).toBe(true);
    const top = a.filter(p => p.y < 20), bot = a.filter(p => p.y > N - 20);
    expect(top.length).toBeGreaterThan(0); expect(bot.length).toBeGreaterThan(0);
  });
});
