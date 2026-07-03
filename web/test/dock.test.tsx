import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Dock from "../src/dock/Dock";
import type { VizData } from "../src/types";

const viz = {
  slug: "x", title: "x", colors: {}, cn: {}, diag: {}, edges: [],
  nodes: [{ id: "t1", type: "theme", label: "訴說的不可能", note: "節點說明", intensity: null,
    evidence: [{ quote: "我們是披上層層雲幕", start: 12, end: 21, pos: 0.3 }] }],
  feedback: {
    read: "這篇在做什麼", one_line: "改這個", minor: [], strengths: [],
    key_points: [{ title: "關鍵", body: "獨白過大", question: "收一半會怎樣?", refs: ["t1"], quotes: [] }],
  },
} as unknown as VizData;

describe("Dock", () => {
  it("無選取顯示總覽", () => {
    render(<Dock slug="x" viz={viz} selected={null} />);
    expect(screen.getByText(/這篇在做什麼/)).toBeTruthy();
  });
  it("選 node 顯示其錨定回饋", () => {
    render(<Dock slug="x" viz={viz} selected="t1" />);
    expect(screen.getByText("訴說的不可能")).toBeTruthy();
    expect(screen.getByText(/獨白過大/)).toBeTruthy();
    expect(screen.getByText(/收一半會怎樣/)).toBeTruthy();
  });
  it("選到帶 evidence 的節點 → 列出引文且按鈕觸發 onJump(start,end)", () => {
    const onJump = vi.fn();
    const { container } = render(<Dock slug="x" viz={viz} selected="t1" onJump={onJump} />);
    expect(screen.getByText(/披上層層雲幕/)).toBeTruthy();
    fireEvent.click(container.querySelector(".dock-jump")!);
    expect(onJump).toHaveBeenCalledWith(12, 21);
  });
});
