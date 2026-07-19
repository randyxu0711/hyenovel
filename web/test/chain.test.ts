import { describe, it, expect } from "vitest";
import { layoutChain, focusSet } from "../src/lib/chain";
import type { VizData } from "../src/types";

const fake = {
  slug: "x", title: "x", colors: {}, cn: {}, feedback: null,
  diag: { k2: ["orphan"], t1: ["overloaded"] },
  nodes: [
    { id: "k1", type: "technique", label: "K1", note: "", intensity: null, evidence: [] },
    { id: "k2", type: "technique", label: "K2", note: "", intensity: null, evidence: [] },
    { id: "e1", type: "effect", label: "E1", note: "", intensity: 0.5, evidence: [] },
    { id: "t1", type: "theme", label: "T1", note: "", intensity: null, evidence: [] },
  ],
  edges: [
    { type: "produces", from: "k1", to: "e1" },
    { type: "serves", from: "e1", to: "t1" },
  ],
} as unknown as VizData;

describe("chain", () => {
  it("layoutChain 三欄 x 遞增、帶診斷 class", () => {
    const { nodes } = layoutChain(fake, 400);
    const k = nodes.find(n => n.id === "k1")!, e = nodes.find(n => n.id === "e1")!, t = nodes.find(n => n.id === "t1")!;
    expect(k.x).toBeLessThan(e.x); expect(e.x).toBeLessThan(t.x);
    expect(nodes.find(n => n.id === "k2")!.classes).toContain("orphan");
    expect(t.classes).toContain("overloaded");
  });
  it("focusSet 沿整條意圖鏈(不只 1 跳):k1 也拉到它服務的 t1", () => {
    expect([...focusSet(fake.edges, "k1")].sort()).toEqual(["e1", "k1", "t1"]);
    expect([...focusSet(fake.edges, "e1")].sort()).toEqual(["e1", "k1", "t1"]);
    expect([...focusSet(fake.edges, "t1")].sort()).toEqual(["e1", "k1", "t1"]);
  });
});
