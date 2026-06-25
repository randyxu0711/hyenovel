import { describe, it, expect } from "vitest";
import { orderedBeats, axisMarks, layoutLane, type LaneItem } from "../src/lib/axis";
import type { VizData, VizNode } from "../src/types";

const item = (id: string, pos: number): LaneItem =>
  ({ node: { id, type: "technique", label: id, note: "", intensity: null, evidence: [] } as VizNode, pos });

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

describe("layoutLane — 泳道內去重疊堆疊", () => {
  it("pos 換算到 x:0→x0、1→x1", () => {
    const out = layoutLane([item("a", 0), item("b", 1)], 70, 930, 60);
    expect(out.find(o => o.node.id === "a")!.x).toBe(70);
    expect(out.find(o => o.node.id === "b")!.x).toBe(930);
  });

  it("分散的點全在第 0 層", () => {
    const out = layoutLane([item("a", 0.1), item("b", 0.5), item("c", 0.9)], 70, 930, 60);
    expect(out.every(o => o.level === 0)).toBe(true);
  });

  it("擠在一起的點往上堆疊(level 遞增)", () => {
    const out = layoutLane([item("a", 0.46), item("b", 0.47), item("c", 0.48)], 70, 930, 60);
    expect(out.map(o => o.level).sort()).toEqual([0, 1, 2]);
  });
});
