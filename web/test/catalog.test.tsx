import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Catalog from "../src/journey/Catalog";
import type { IndexEntry } from "../src/types";


const entries: IndexEntry[] = [
  { slug: "s01", title: "長夜", synopsis: "...", nodes: 43, edges: 61, has_feedback: true, has_viz: true, updated: "" },
  { slug: "s02", title: "鬣狗", synopsis: "...", nodes: 38, edges: 49, has_feedback: true, has_viz: true, updated: "" },
];

describe("Catalog", () => {
  it("每篇一個 story 元素", () => {
    render(<MemoryRouter><Catalog entries={entries} /></MemoryRouter>);
    expect(screen.getAllByTestId("story").length).toBe(2);
    expect(screen.getByText("長夜")).toBeTruthy();
  });
  it("空陣列顯示空狀態", () => {
    render(<MemoryRouter><Catalog entries={[]} /></MemoryRouter>);
    expect(screen.getByText(/還沒有故事/)).toBeTruthy();
  });
});
