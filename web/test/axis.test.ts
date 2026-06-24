import { describe, it, expect } from "vitest";
import { orderedBeats, axisMarks } from "../src/lib/axis";
import type { VizData } from "../src/types";

const fake = {
  slug: "x", title: "x", colors: {}, cn: {}, diag: {}, feedback: null,
  nodes: [
    { id: "b2", type: "beat", label: "B2", note: "", intensity: 0.8, evidence: [] },
    { id: "b1", type: "beat", label: "B1", note: "", intensity: 0.2, evidence: [] },
    { id: "k1", type: "technique", label: "K", note: "", intensity: null,
      evidence: [{ quote: "q", start: 0, end: 1, pos: 0.5 }] },
  ],
  edges: [{ type: "precedes", from: "b1", to: "b2" }],
} as unknown as VizData;

describe("axis", () => {
  it("orderedBeats 依 precedes 串", () => {
    expect(orderedBeats(fake).map(b => b.id)).toEqual(["b1", "b2"]);
  });
  it("axisMarks 取有 pos 的技法/效果", () => {
    const m = axisMarks(fake);
    expect(m).toHaveLength(1);
    expect(m[0].pos).toBe(0.5);
  });
});
