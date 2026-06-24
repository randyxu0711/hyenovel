import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import IntentionChain from "../src/viz/IntentionChain";
import viz from "./fixtures/viz.json";
import type { VizData } from "../src/types";

describe("IntentionChain", () => {
  it("渲染節點且診斷 class 落在對應節點", () => {
    const v = viz as unknown as VizData;
    const { container } = render(<IntentionChain viz={v} selected={null} onPick={vi.fn()} />);
    const groups = container.querySelectorAll("g.cnode");
    const expected = v.nodes.filter(n => ["technique","effect","theme"].includes(n.type)).length;
    expect(groups.length).toBe(expected);
    // 任一個有 diag 的節點,對應 g 應帶該 class
    const diagId = Object.keys(v.diag)[0];
    if (diagId) {
      const g = container.querySelector(`g.cnode[data-id="${diagId}"]`);
      expect(g?.className.baseVal).toMatch(/orphan|overloaded|hollow/);
    }
  });
});
