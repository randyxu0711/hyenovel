import { describe, it, expect } from "vitest";
import { spline } from "../src/lib/spline";

describe("spline", () => {
  it("spline 以 M 開頭、含 C 段", () => {
    const d = spline([[0, 0], [10, 10], [20, 0]]);
    expect(d.startsWith("M0,0")).toBe(true);
    expect(d).toContain("C");
  });
});
