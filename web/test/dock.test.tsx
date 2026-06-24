import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Dock from "../src/dock/Dock";
import type { VizData } from "../src/types";

const viz = {
  slug: "x", title: "x", colors: {}, cn: {}, diag: {}, edges: [],
  nodes: [{ id: "t1", type: "theme", label: "訴說的不可能", note: "節點說明", intensity: null, evidence: [] }],
  feedback: {
    read: "這篇在做什麼", one_line: "改這個", minor: [], strengths: [],
    key_points: [{ title: "關鍵", body: "獨白過大", question: "收一半會怎樣?", refs: ["t1"], quotes: [] }],
  },
} as unknown as VizData;

describe("Dock", () => {
  it("無選取顯示總覽", () => {
    render(<Dock viz={viz} selected={null} />);
    expect(screen.getByText(/這篇在做什麼/)).toBeTruthy();
  });
  it("選 node 顯示其錨定回饋", () => {
    render(<Dock viz={viz} selected="t1" />);
    expect(screen.getByText("訴說的不可能")).toBeTruthy();
    expect(screen.getByText(/獨白過大/)).toBeTruthy();
    expect(screen.getByText(/收一半會怎樣/)).toBeTruthy();
  });
});
