import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import viz from "./fixtures/viz.json";

vi.mock("../src/data/client", () => ({
  getTranscript: vi.fn(async () => ({ turns: [] })),
  getStory: vi.fn(async () => ({ viz, source: "　　原文。" })),
  getConclusions: vi.fn(async () => ({ conclusions: [] })),
}));
import Single from "../src/journey/Single";

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
});

describe("Single 用量 tab(4a 期間隱藏)", () => {
  it("文字分頁只剩原文/回饋,沒有『用量』", async () => {
    render(<MemoryRouter initialEntries={["/story/s02"]}>
      <Routes><Route path="/story/:slug" element={<Single />} /></Routes></MemoryRouter>);
    await waitFor(() => expect(document.querySelector(".sb-bar")).toBeTruthy());
    const labels = [...document.querySelectorAll(".sb-textabs button")].map(b => b.textContent);
    expect(labels).toEqual(["原文", "回饋"]);
  });
});
